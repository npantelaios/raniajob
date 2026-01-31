"""Workday career site scraper using their JSON API.

Workday career sites have a hidden JSON API that allows scraping without browser automation.
This module implements a scraper that uses this API to fetch job listings.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import requests

from ..models import JobPosting
from ..location_filters import filter_jobs_by_location, get_default_target_states


# Workday URLs for major pharma companies (12 companies use Workday)
WORKDAY_PHARMA_URLS = {
    "pfizer": "https://pfizer.wd1.myworkdayjobs.com/PfizerCareers",
    "amgen": "https://amgen.wd1.myworkdayjobs.com/Careers",
    "regeneron": "https://regeneron.wd1.myworkdayjobs.com/Careers",
    "novartis": "https://novartis.wd3.myworkdayjobs.com/Novartis_Careers",
    "roche": "https://roche.wd3.myworkdayjobs.com/roche-ext",
    "sanofi": "https://sanofi.wd3.myworkdayjobs.com/SanofiCareers",
    "lilly": "https://lilly.wd5.myworkdayjobs.com/en-US/LLY",
    "merck": "https://msd.wd5.myworkdayjobs.com/SearchJobs",
    "thermofisher": "https://thermofisher.wd5.myworkdayjobs.com/ThermoFisherCareers",
    "bms": "https://bristolmyerssquibb.wd5.myworkdayjobs.com/BMS",
    "gsk": "https://gsk.wd5.myworkdayjobs.com/GSKCareers",
    "vertex": "https://vrtx.wd5.myworkdayjobs.com/en-US/Vertex_Careers",
}


def parse_workday_site(
    pages: List[str], site_config, base_url: str, source: str
) -> List[JobPosting]:
    """
    Scrape Workday career portal using their JSON API.

    The 'pages' parameter is ignored - we use the site config's workday_url instead.
    Supports both search_terms (list) and search_term (string) for backwards compatibility.
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Get configuration
    workday_url = getattr(site_config, "workday_url", None)
    if not workday_url:
        logger.error(f"No workday_url configured for site: {source}")
        return []

    # Support both search_terms (list) and search_term (string) for backwards compatibility
    search_terms = getattr(site_config, "search_terms", None)
    if not search_terms:
        # Fallback to single search_term
        single_term = getattr(site_config, "search_term", None)
        search_terms = [single_term] if single_term else [""]  # Empty string = all jobs

    max_results = getattr(site_config, "max_results", 10000)  # No limit by default

    logger.info(f"Workday: Scraping {workday_url} with {len(search_terms)} search terms")

    try:
        all_jobs: List[JobPosting] = []
        seen_urls: set = set()

        # Iterate through each search term
        for search_term in search_terms:
            logger.info(f"Workday: Searching '{search_term}' on {source}")
            jobs = _fetch_workday_jobs(workday_url, search_term, max_results, source, logger)

            # Deduplicate by URL
            for job in jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

            # Small delay between searches to be respectful
            if len(search_terms) > 1:
                time.sleep(1)

        logger.info(f"Workday: Found {len(all_jobs)} unique jobs from {source}")

        # Apply US location filtering (MA, NY, NJ, PA only)
        target_states = get_default_target_states()
        filtered_jobs = filter_jobs_by_location(all_jobs, target_states)
        logger.info(f"Workday: After US location filter (MA/NY/NJ/PA): {len(filtered_jobs)}/{len(all_jobs)} jobs from {source}")

        return filtered_jobs
    except Exception as e:
        logger.error(f"Workday: Error scraping {source}: {e}")
        return []


def _fetch_workday_jobs(
    workday_url: str,
    search_term: Optional[str],
    max_results: int,
    source: str,
    logger: logging.Logger,
) -> List[JobPosting]:
    """Fetch jobs from Workday using their JSON API."""
    jobs: List[JobPosting] = []

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    # Step 1: Hit the main URL to get the initial page data and pagination endpoint
    try:
        # The Workday API endpoint pattern
        # Example: https://pfizer.wd1.myworkdayjobs.com/wday/cxs/pfizer/PfizerCareers/jobs
        # We need to construct the API URL from the career site URL

        # Parse the base URL to construct API endpoint
        parts = workday_url.rstrip("/").split("/")
        # URL format: https://{company}.wd{N}.myworkdayjobs.com/{CareerSite}
        # Handle URLs with extra path segments like /en-US/LLY
        domain = "/".join(parts[:3])  # https://pfizer.wd1.myworkdayjobs.com

        # Find the career site name (last non-language segment)
        career_site = parts[-1]
        if career_site.lower() in ["en", "en-us", "en-gb", "de", "fr"]:
            career_site = parts[-2] if len(parts) > 4 else parts[-1]

        # Extract company name from subdomain
        company_subdomain = parts[2].split(".")[0]  # pfizer

        # Construct API URL
        api_url = f"{domain}/wday/cxs/{company_subdomain}/{career_site}/jobs"

        logger.info(f"Workday API URL: {api_url}")

        # Step 2: Make initial request to get total count (with retry)
        payload = {
            "appliedFacets": {},
            "limit": 20,
            "offset": 0,
            "searchText": search_term or "",
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.post(api_url, json=payload, headers=headers, timeout=7)

                # Handle 4XX errors gracefully
                if 400 <= resp.status_code < 500:
                    logger.warning(f"Workday: {source} returned {resp.status_code} - skipping this company")
                    return []

                resp.raise_for_status()
                data = resp.json()
                break  # Success

            except requests.exceptions.HTTPError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Workday: {source} attempt {attempt + 1} failed, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Workday: {source} failed after {max_retries} attempts - skipping")
                    return []
            except requests.exceptions.RequestException as e:
                logger.error(f"Workday: {source} connection error: {e} - skipping")
                return []

        total_count = data.get("total", 0)
        logger.info(f"Workday: {source} has {total_count} total jobs available")

        if total_count == 0:
            logger.info(f"Workday: {source} returned 0 jobs - moving to next company")
            return []

        # Process first batch
        job_postings = data.get("jobPostings", [])
        for job_data in job_postings:
            job = _parse_workday_job(job_data, workday_url, source)
            if job:
                jobs.append(job)

        # Step 3: Paginate through remaining results
        offset = 20
        consecutive_errors = 0
        max_consecutive_errors = 3

        while offset < min(total_count, max_results):
            time.sleep(0.5)  # Be respectful

            payload["offset"] = offset
            payload["limit"] = 20

            try:
                resp = requests.post(api_url, json=payload, headers=headers, timeout=7)

                # Handle 4XX errors during pagination
                if 400 <= resp.status_code < 500:
                    logger.warning(f"Workday: {source} pagination got {resp.status_code} at offset {offset} - stopping pagination")
                    break

                resp.raise_for_status()
                data = resp.json()
                consecutive_errors = 0  # Reset on success

                job_postings = data.get("jobPostings", [])
                if not job_postings:
                    break

                for job_data in job_postings:
                    job = _parse_workday_job(job_data, workday_url, source)
                    if job:
                        jobs.append(job)

                logger.debug(f"Workday: {source} fetched {offset + len(job_postings)}/{total_count} jobs")
                offset += 20

            except Exception as e:
                consecutive_errors += 1
                logger.warning(f"Workday: {source} error at offset {offset}: {e}")

                if consecutive_errors >= max_consecutive_errors:
                    logger.warning(f"Workday: {source} too many consecutive errors - stopping pagination")
                    break

                time.sleep(1)  # Brief pause before retry
                continue

        logger.info(f"Workday: {source} successfully scraped {len(jobs)} jobs")
        return jobs

    except requests.exceptions.HTTPError as e:
        if hasattr(e, 'response') and e.response is not None:
            status_code = e.response.status_code
            if 400 <= status_code < 500:
                logger.warning(f"Workday: {source} returned HTTP {status_code} - skipping this company")
            else:
                logger.error(f"Workday: {source} HTTP error {status_code}: {e}")
        else:
            logger.error(f"Workday: {source} HTTP error: {e}")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Workday: {source} request failed: {e} - skipping")
        return []
    except Exception as e:
        logger.error(f"Workday: {source} unexpected error: {e} - skipping")
        return []


def _validate_date_sanity_workday(dt: Optional[datetime], max_age_days: int = 365) -> Optional[datetime]:
    """Validate Workday date sanity.

    Args:
        dt: Date to validate
        max_age_days: Maximum age in days (default 365)

    Returns:
        Validated datetime or None if invalid
    """
    if not dt:
        return None

    now = datetime.now(timezone.utc)

    # Reject dates older than max_age_days
    if dt < now - timedelta(days=max_age_days):
        logging.getLogger(__name__).warning(
            f"Rejecting Workday date {dt.date()} - older than {max_age_days} days"
        )
        return None

    # Reject dates more than 30 days in future
    if dt > now + timedelta(days=30):
        logging.getLogger(__name__).warning(
            f"Rejecting Workday date {dt.date()} - more than 30 days in future"
        )
        return None

    return dt


def _parse_workday_job(
    job_data: Dict[str, Any], base_url: str, source: str
) -> Optional[JobPosting]:
    """Parse a single Workday job posting from JSON."""
    from datetime import timedelta
    import re
    from ..filters import extract_all_dates

    try:
        title = job_data.get("title", "").strip()
        if not title:
            return None

        # Build the job URL
        external_path = job_data.get("externalPath", "")
        if external_path:
            job_url = urljoin(base_url.rstrip("/") + "/", external_path.lstrip("/"))
        else:
            job_url = base_url

        # Extract location
        location_parts = []
        if job_data.get("locationsText"):
            location_parts.append(job_data["locationsText"])

        location = ", ".join(location_parts) if location_parts else None

        # Extract posted date - check multiple possible field names
        date_posted = None
        posted_date_fields = [
            "postedOn", "postedDate", "postingDate", "datePosted",
            "publishedDate", "startDate", "createdDate", "openDate"
        ]
        for field in posted_date_fields:
            field_value = job_data.get(field)
            if field_value:
                try:
                    # Workday typically returns dates like "Posted 30+ Days Ago" or "Posted Today"
                    # or ISO format dates
                    field_str = str(field_value)
                    dt = None
                    if "Today" in field_str:
                        dt = datetime.now(timezone.utc)
                    elif "Yesterday" in field_str:
                        dt = datetime.now(timezone.utc) - timedelta(days=1)
                    elif "Days Ago" in field_str or "days ago" in field_str:
                        # Handle "30+ Days Ago" format
                        match = re.search(r"(\d+)\+?", field_str)
                        if match:
                            days = int(match.group(1))
                            dt = datetime.now(timezone.utc) - timedelta(days=days)
                    else:
                        # Try ISO format
                        dt = datetime.fromisoformat(field_str.replace("Z", "+00:00"))

                    # Validate date sanity
                    if dt:
                        date_posted = _validate_date_sanity_workday(dt)
                        if date_posted:
                            break  # Found a valid date, stop checking other fields
                except Exception:
                    continue  # Try next field

        # Extract expiration/closing date if available
        expiration_date = None
        end_date_fields = ["endDate", "closingDate", "expirationDate", "applicationDeadline", "postingEndDate"]
        for field in end_date_fields:
            if job_data.get(field):
                try:
                    field_value = job_data[field]
                    dt = None
                    if isinstance(field_value, str):
                        dt = datetime.fromisoformat(field_value.replace("Z", "+00:00"))

                    # Validate date sanity
                    if dt:
                        expiration_date = _validate_date_sanity_workday(dt)
                        if expiration_date:
                            break
                except Exception:
                    continue

        # Extract company name from source or use site name
        company = source.replace("_careers", "").replace("_", " ").title()

        # Build description from ALL available text fields
        description_parts = []

        # Primary description fields
        desc_fields = [
            "jobDescription", "description", "jobPostingDescription",
            "requisitionDescription", "summary", "jobSummary", "overview"
        ]
        for field in desc_fields:
            if job_data.get(field):
                description_parts.append(str(job_data[field]))

        # Bullet fields (usually a summary)
        if job_data.get("bulletFields"):
            for bullet in job_data["bulletFields"]:
                description_parts.append(str(bullet))

        # Job category/type fields that might contain relevant keywords
        category_fields = [
            "jobCategory", "jobType", "jobFamily", "jobFamilyGroup",
            "managementLevel", "workerSubType", "jobProfile", "primaryJobFamily"
        ]
        for field in category_fields:
            if job_data.get(field):
                description_parts.append(str(job_data[field]))

        # Look for salary information - ONLY if it has $ symbol
        salary_info = None
        salary_fields = ["salary", "compensation", "payRange", "salaryRange", "pay", "wage"]
        for field in salary_fields:
            if job_data.get(field):
                field_value = str(job_data[field])
                # Only use if it contains $ symbol
                if '$' in field_value:
                    salary_info = field_value
                    break

        # Also check bulletFields for salary with $ symbol only
        if not salary_info and description_parts:
            for part in description_parts:
                # Only match if $ is directly before the number
                match = re.search(r'\$[\d,]+(?:\.\d{2})?\s*[kK]?(?:\s*[-–]\s*\$[\d,]+(?:\.\d{2})?\s*[kK]?)?', str(part))
                if match:
                    salary_info = match.group(0)
                    break

        # Add salary to description if found (must have $)
        if salary_info and '$' in salary_info:
            description_parts.append(f"Salary: {salary_info}")

        description = " | ".join(description_parts) if description_parts else ""

        # Also extract dates from description if not found from fields
        # Note: extract_all_dates now has built-in sanity checking
        if not date_posted or not expiration_date:
            desc_posted, desc_expiration = extract_all_dates(description)
            # Validate dates from description extraction
            if not date_posted and desc_posted:
                date_posted = _validate_date_sanity_workday(desc_posted)
            if not expiration_date and desc_expiration:
                expiration_date = _validate_date_sanity_workday(desc_expiration)

        return JobPosting(
            title=title,
            company=company,
            url=job_url,
            description=description,
            date_posted=date_posted,
            source=f"{source}_workday",
            location=location,
            expiration_date=expiration_date,
        )

    except Exception as e:
        logging.getLogger(__name__).warning(f"Workday: Failed to parse job: {e}")
        return None
