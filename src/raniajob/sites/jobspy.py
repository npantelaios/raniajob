from __future__ import annotations

import logging
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple

from ..models import JobPosting

# Regex patterns to extract JSON-LD date fields from Indeed HTML/description
# Matches: "datePosted":"2026-01-16T22:02:28.162Z"
_DATE_POSTED_JSON_RE = re.compile(r'"datePosted"\s*:\s*"([^"]+)"')
# Matches: "validThrough":"2026-05-21T00:27:38.974Z"
_VALID_THROUGH_JSON_RE = re.compile(r'"validThrough"\s*:\s*"([^"]+)"')
from ..location_filters import (
    filter_jobs_by_location,
    get_default_target_states,
    get_target_state_locations,
)

try:
    from jobspy import scrape_jobs
    import pandas as pd
except ImportError as exc:
    print(
        "Warning: JobSpy not available. Install with: pip install python-jobspy",
        file=sys.stderr,
    )
    scrape_jobs = None
    pd = None


def parse_jobspy_sites(
    pages: List[str], site_config, base_url: str, source: str, fetcher=None
) -> List[JobPosting]:
    """
    JobSpy parser that uses the JobSpy library to scrape job sites directly.
    This bypasses the normal HTML parsing and uses JobSpy's API instead.

    The 'pages' parameter is ignored for JobSpy - we use the site config directly.

    Args:
        pages: Ignored for JobSpy
        site_config: Site configuration
        base_url: Base URL (ignored for JobSpy)
        source: Source name for job postings
        fetcher: Optional Fetcher instance for HTML fetching to extract dates

    Returns:
        List of JobPosting objects
    """
    if scrape_jobs is None:
        print(
            "ERROR: JobSpy not available - install with: pip install python-jobspy",
            file=sys.stderr,
        )
        return []

    # Set up logging for detailed debugging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Create fetcher if not provided (for HTML fetching to extract dates)
    if fetcher is None:
        from ..fetcher import Fetcher
        fetcher = Fetcher()
        logger.info("Created Fetcher instance for HTML date extraction")

    try:
        # Extract JobSpy configuration from site_config with validation
        search_terms = getattr(
            site_config, "search_terms", ["CRISPR", "molecular biology", "biotech"]
        )
        if not search_terms:
            search_terms = ["biotech", "scientist", "researcher"]  # Fallback terms
            logger.warning("No search terms provided, using fallback terms")

        # Use target state locations if not specified
        locations = getattr(site_config, "locations", None)
        if not locations:
            locations = get_target_state_locations()
            logger.info(f"Using default target state locations: {locations}")

        job_sites = getattr(site_config, "job_sites", ["indeed"])
        if not job_sites:
            job_sites = ["indeed"]  # Fallback to Indeed as most reliable
            logger.warning("No job sites specified, using Indeed as fallback")

        # No limits - get all available jobs
        results_wanted = getattr(
            site_config, "results_wanted", 1000
        )  # High default to get all jobs
        hours_old = getattr(site_config, "hours_old", 168)  # Increased to 7 days

        # Get target states for filtering
        target_states = get_default_target_states()
        logger.info(f"Target states for filtering: {target_states}")

        all_jobs = []
        search_stats = {
            "total_searches": 0,
            "successful_searches": 0,
            "failed_searches": 0,
            "total_jobs_found": 0,
        }

        # Search each combination of search terms and locations with comprehensive error handling
        for search_term in search_terms:
            for location in locations:
                search_stats["total_searches"] += 1
                retry_count = 0
                max_retries = 3

                while retry_count < max_retries:
                    try:
                        logger.info(
                            f"JobSpy: Searching '{search_term}' in '{location}' on {job_sites} (attempt {retry_count + 1})"
                        )

                        # IMPORTANT: JobSpy has parameter conflicts!
                        # Only ONE of these can be used: hours_old, job_type, is_remote, easy_apply
                        # We use only hours_old as it's most useful for finding recent jobs
                        search_params = {
                            "site_name": job_sites,
                            "search_term": search_term,
                            "location": location,
                            "results_wanted": results_wanted,
                            "hours_old": hours_old,  # Keep only this filter
                            "country_indeed": "USA",
                        }

                        logger.info(
                            f"JobSpy search params: {search_params}"
                        )

                        jobs_df = scrape_jobs(**search_params)

                        if jobs_df is not None and not jobs_df.empty:
                            # Log per-site results
                            if "site" in jobs_df.columns:
                                site_counts = jobs_df["site"].value_counts().to_dict()
                                logger.info(
                                    f"JobSpy results by site for '{search_term}' in '{location}': {site_counts}"
                                )
                            else:
                                logger.info(
                                    f"Found {len(jobs_df)} jobs for '{search_term}' in '{location}'"
                                )

                            # Convert DataFrame to JobPosting objects (with fetcher for HTML date extraction)
                            jobs = _convert_dataframe_to_jobs(jobs_df, source, fetcher)
                            all_jobs.extend(jobs)
                            search_stats["successful_searches"] += 1
                            search_stats["total_jobs_found"] += len(jobs)
                            logger.info(
                                f"JobSpy: Successfully found {len(jobs)} jobs for '{search_term}' in '{location}'"
                            )
                            # Add delay between searches to be respectful
                            time.sleep(2)
                            break  # Success, exit retry loop
                        else:
                            raise Exception("No jobs found")

                    except Exception as e:
                        retry_count += 1
                        search_stats["failed_searches"] += 1
                        logger.warning(
                            f"JobSpy search attempt {retry_count} failed for '{search_term}' in '{location}': {e}"
                        )

                        if retry_count < max_retries:
                            # Exponential backoff
                            wait_time = 2**retry_count
                            logger.info(f"Retrying in {wait_time} seconds...")
                            time.sleep(wait_time)
                        else:
                            logger.error(
                                f"All {max_retries} attempts failed for '{search_term}' in '{location}'"
                            )
                            break

        # Log comprehensive search statistics
        logger.info(f"JobSpy Search Statistics:")
        logger.info(f"  Total searches attempted: {search_stats['total_searches']}")
        logger.info(f"  Successful searches: {search_stats['successful_searches']}")
        logger.info(f"  Failed searches: {search_stats['failed_searches']}")
        logger.info(
            f"  Total jobs found before filtering: {search_stats['total_jobs_found']}"
        )
        logger.info(f"  Unique jobs before location filtering: {len(all_jobs)}")

        # Apply location filtering to ensure only NY, NJ, PA, MA jobs
        filtered_jobs = filter_jobs_by_location(all_jobs, target_states)
        jobs_removed = len(all_jobs) - len(filtered_jobs)

        logger.info(
            f"JobSpy: Location filtering kept {len(filtered_jobs)}/{len(all_jobs)} jobs"
        )
        if jobs_removed > 0:
            logger.info(
                f"JobSpy: Location filtering removed {jobs_removed} jobs outside target states"
            )
            # Log some examples of removed locations for debugging
            removed_locations = []
            for job in all_jobs:
                if job not in filtered_jobs and job.location:
                    removed_locations.append(job.location)
            if removed_locations:
                unique_removed = list(
                    set(removed_locations[:5])
                )  # Show up to 5 examples
                logger.info(f"JobSpy: Example removed locations: {unique_removed}")

        return filtered_jobs

    except Exception as e:
        logger.error(f"JobSpy critical error: {e}")
        logger.exception("Full exception details:")
        return []


def _parse_iso_datetime(date_str: str) -> Optional[datetime]:
    """Parse ISO 8601 datetime string to datetime object.

    Handles formats like:
    - 2026-01-16T22:02:28.162Z
    - 2026-01-16T22:02:28Z
    - 2026-01-16
    """
    if not date_str:
        return None
    try:
        # Handle Z suffix (UTC)
        date_str = date_str.replace("Z", "+00:00")
        # Handle milliseconds - fromisoformat doesn't like more than 6 decimal places
        if "." in date_str:
            parts = date_str.split(".")
            if len(parts) == 2:
                # Truncate microseconds to 6 digits max
                decimal_part = parts[1]
                tz_part = ""
                if "+" in decimal_part:
                    decimal_part, tz_part = decimal_part.split("+")
                    tz_part = "+" + tz_part
                elif "-" in decimal_part and len(decimal_part) > 6:
                    # Might be timezone like -05:00
                    idx = decimal_part.rfind("-")
                    if idx > 0:
                        tz_part = decimal_part[idx:]
                        decimal_part = decimal_part[:idx]
                decimal_part = decimal_part[:6]
                date_str = f"{parts[0]}.{decimal_part}{tz_part}"

        parsed = datetime.fromisoformat(date_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, OverflowError):
        return None


def _extract_json_ld_dates(text: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Extract datePosted and validThrough from JSON-LD structured data in text.

    Indeed.com embeds these in their HTML like:
    - "datePosted":"2026-01-16T22:02:28.162Z"
    - "validThrough":"2026-05-21T00:27:38.974Z"

    Returns:
        (date_posted, expiration_date) tuple
    """
    date_posted = None
    expiration_date = None

    # Extract datePosted
    match = _DATE_POSTED_JSON_RE.search(text)
    if match:
        date_posted = _parse_iso_datetime(match.group(1))

    # Extract validThrough (expiration date)
    match = _VALID_THROUGH_JSON_RE.search(text)
    if match:
        expiration_date = _parse_iso_datetime(match.group(1))

    return (date_posted, expiration_date)


def _validate_date_sanity(dt: Optional[datetime], max_age_days: int = 365) -> Optional[datetime]:
    """Validate date is not too old or too far in future.

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
            f"Rejecting date {dt.date()} - older than {max_age_days} days"
        )
        return None

    # Reject dates more than 30 days in future
    if dt > now + timedelta(days=30):
        logging.getLogger(__name__).warning(
            f"Rejecting date {dt.date()} - more than 30 days in future"
        )
        return None

    return dt


def _convert_dataframe_to_jobs(df: pd.DataFrame, source: str, fetcher=None) -> List[JobPosting]:
    """Convert JobSpy DataFrame to JobPosting objects.

    Args:
        df: JobSpy DataFrame with job data
        source: Source name for job postings
        fetcher: Optional Fetcher instance for HTML fetching

    Returns:
        List of JobPosting objects
    """
    from ..filters import extract_all_dates

    jobs = []
    html_fetch_count = 0
    MAX_HTML_FETCHES = 50  # Limit per batch to avoid anti-bot triggers
    logger = logging.getLogger(__name__)

    for _, row in df.iterrows():
        try:
            # Tier 1: Parse date_posted if available from JobSpy DataFrame
            date_posted: Optional[datetime] = None
            if pd.notna(row.get("date_posted")):
                try:
                    # JobSpy typically returns dates as pandas timestamps
                    if isinstance(row["date_posted"], pd.Timestamp):
                        dt = row["date_posted"].to_pydatetime()
                        # Ensure timezone aware
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        # Validate date sanity
                        date_posted = _validate_date_sanity(dt)
                except Exception:
                    date_posted = None

            # Check for expiration_date field from JobSpy
            expiration_date: Optional[datetime] = None
            for exp_field in ["job_expiration_date", "expiration_date", "closing_date", "application_deadline", "valid_through"]:
                if pd.notna(row.get(exp_field)):
                    try:
                        if isinstance(row[exp_field], pd.Timestamp):
                            dt = row[exp_field].to_pydatetime()
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            # Validate date sanity
                            expiration_date = _validate_date_sanity(dt)
                            if expiration_date:
                                break
                    except Exception:
                        continue

            # Extract and clean fields
            title = str(row.get("title", "")).strip()
            company = str(row.get("company", "")).strip()
            url = str(row.get("job_url", "")).strip()
            description = str(row.get("description", "")).strip()
            location = (
                str(row.get("location", "")).strip()
                if pd.notna(row.get("location"))
                else None
            )

            # Skip jobs with missing essential data
            if not title or not company or not url:
                continue

            # Tier 2: Fetch Indeed HTML to extract JSON-LD datePosted
            # Only if date_posted is still missing and we have a fetcher
            if not date_posted and 'indeed.com' in url.lower() and fetcher:
                if html_fetch_count < MAX_HTML_FETCHES:
                    try:
                        logger.info(f"Fetching Indeed HTML for date extraction: {url}")
                        html_content = fetcher.get(url)
                        if html_content:
                            json_ld_posted, json_ld_expiration = _extract_json_ld_dates(html_content)
                            if json_ld_posted:
                                date_posted = _validate_date_sanity(json_ld_posted)
                                logger.info(f"Extracted date_posted from Indeed HTML: {date_posted}")
                            if not expiration_date and json_ld_expiration:
                                expiration_date = _validate_date_sanity(json_ld_expiration)
                                logger.info(f"Extracted expiration_date from Indeed HTML: {expiration_date}")
                        html_fetch_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to fetch HTML for {url}: {e}")
                else:
                    logger.info(f"Reached HTML fetch limit ({MAX_HTML_FETCHES}), skipping HTML fetch for remaining jobs")

            # Combine multiple description fields if available
            full_description = description
            if pd.notna(row.get("job_function")):
                full_description += f" Functions: {row['job_function']}"
            if pd.notna(row.get("benefits")):
                full_description += f" Benefits: {row['benefits']}"

            # Tier 3: Extract dates from description using extract_all_dates()
            # Note: extract_all_dates now has built-in sanity checking
            if not date_posted or not expiration_date:
                desc_posted, desc_expiration = extract_all_dates(full_description)

                # Use description extraction as fallback, with validation
                if not date_posted and desc_posted:
                    date_posted = _validate_date_sanity(desc_posted)
                if not expiration_date and desc_expiration:
                    expiration_date = _validate_date_sanity(desc_expiration)

            # Tier 4: Try JSON-LD on Markdown as last resort (rarely works)
            if not date_posted or not expiration_date:
                json_ld_posted, json_ld_expiration = _extract_json_ld_dates(full_description)
                if not date_posted and json_ld_posted:
                    date_posted = _validate_date_sanity(json_ld_posted)
                if not expiration_date and json_ld_expiration:
                    expiration_date = _validate_date_sanity(json_ld_expiration)

            job = JobPosting(
                title=title,
                company=company,
                url=url,
                description=full_description,
                date_posted=date_posted,
                source=f"{source}_jobspy",
                location=location,
                expiration_date=expiration_date,
            )

            jobs.append(job)

        except Exception as e:
            print(f"JobSpy warning: Failed to parse job row: {e}", file=sys.stderr)
            continue

    return jobs
