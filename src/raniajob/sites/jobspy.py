from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from ..models import JobPosting
from ..location_filters import filter_jobs_by_location, get_default_target_states, get_target_state_locations

try:
    from jobspy import scrape_jobs
    import pandas as pd
except ImportError as exc:
    print("Warning: JobSpy not available. Install with: pip install python-jobspy", file=sys.stderr)
    scrape_jobs = None
    pd = None


def parse_jobspy_sites(pages: List[str], site_config, base_url: str, source: str) -> List[JobPosting]:
    """
    JobSpy parser that uses the JobSpy library to scrape job sites directly.
    This bypasses the normal HTML parsing and uses JobSpy's API instead.

    The 'pages' parameter is ignored for JobSpy - we use the site config directly.
    """
    if scrape_jobs is None:
        print("ERROR: JobSpy not available - install with: pip install python-jobspy", file=sys.stderr)
        return []

    # Set up logging for detailed debugging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        # Extract JobSpy configuration from site_config with validation
        search_terms = getattr(site_config, 'search_terms', ['CRISPR', 'molecular biology', 'biotech'])
        if not search_terms:
            search_terms = ['biotech', 'scientist', 'researcher']  # Fallback terms
            logger.warning("No search terms provided, using fallback terms")

        # Use target state locations if not specified
        locations = getattr(site_config, 'locations', None)
        if not locations:
            locations = get_target_state_locations()
            logger.info(f"Using default target state locations: {locations}")

        job_sites = getattr(site_config, 'job_sites', ['indeed'])
        if not job_sites:
            job_sites = ['indeed']  # Fallback to Indeed as most reliable
            logger.warning("No job sites specified, using Indeed as fallback")

        # Increase limits and make more permissive
        results_wanted = getattr(site_config, 'results_wanted', 100)  # Increased from 50
        hours_old = getattr(site_config, 'hours_old', 168)  # Increased to 7 days

        # Get target states for filtering
        target_states = get_default_target_states()
        logger.info(f"Target states for filtering: {target_states}")

        all_jobs = []
        search_stats = {'total_searches': 0, 'successful_searches': 0, 'failed_searches': 0, 'total_jobs_found': 0}

        # Search each combination of search terms and locations with comprehensive error handling
        for search_term in search_terms:
            for location in locations:
                search_stats['total_searches'] += 1
                retry_count = 0
                max_retries = 3

                while retry_count < max_retries:
                    try:
                        logger.info(f"JobSpy: Searching '{search_term}' in '{location}' on {job_sites} (attempt {retry_count + 1})")

                        # Try different job type combinations for better results
                        job_types_to_try = [None, "fulltime", "parttime", "contract"]
                        remote_options = [False, True]  # Try both remote and on-site

                        jobs_found_this_search = []

                        for job_type in job_types_to_try:
                            for is_remote in remote_options:
                                try:
                                    search_params = {
                                        'site_name': job_sites,
                                        'search_term': search_term,
                                        'location': location,
                                        'results_wanted': results_wanted,
                                        'hours_old': hours_old,
                                        'is_remote': is_remote,
                                        'country_indeed': "USA"
                                    }

                                    # Only add job_type if it's not None
                                    if job_type:
                                        search_params['job_type'] = job_type

                                    logger.debug(f"Trying search with params: job_type={job_type}, is_remote={is_remote}")

                                    jobs_df = scrape_jobs(**search_params)

                                    if jobs_df is not None and not jobs_df.empty:
                                        logger.info(f"Found {len(jobs_df)} raw jobs for {search_term} in {location} (job_type={job_type}, remote={is_remote})")
                                        jobs_found_this_search.append(jobs_df)

                                    # Add small delay between API calls to be respectful
                                    time.sleep(1)

                                except Exception as search_error:
                                    logger.debug(f"Search variant failed (job_type={job_type}, remote={is_remote}): {search_error}")
                                    continue

                        # Combine all DataFrames from this search
                        if jobs_found_this_search:
                            combined_df = pd.concat(jobs_found_this_search, ignore_index=True)
                            # Remove duplicates based on job_url
                            combined_df = combined_df.drop_duplicates(subset=['job_url'], keep='first')

                            # Convert DataFrame to JobPosting objects
                            jobs = _convert_dataframe_to_jobs(combined_df, source)
                            all_jobs.extend(jobs)
                            search_stats['successful_searches'] += 1
                            search_stats['total_jobs_found'] += len(jobs)
                            logger.info(f"JobSpy: Successfully found {len(jobs)} unique jobs for '{search_term}' in '{location}'")
                            break  # Success, exit retry loop
                        else:
                            raise Exception("No jobs found with any search variant")

                    except Exception as e:
                        retry_count += 1
                        search_stats['failed_searches'] += 1
                        logger.warning(f"JobSpy search attempt {retry_count} failed for '{search_term}' in '{location}': {e}")

                        if retry_count < max_retries:
                            # Exponential backoff
                            wait_time = 2 ** retry_count
                            logger.info(f"Retrying in {wait_time} seconds...")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"All {max_retries} attempts failed for '{search_term}' in '{location}'")
                            break

        # Log comprehensive search statistics
        logger.info(f"JobSpy Search Statistics:")
        logger.info(f"  Total searches attempted: {search_stats['total_searches']}")
        logger.info(f"  Successful searches: {search_stats['successful_searches']}")
        logger.info(f"  Failed searches: {search_stats['failed_searches']}")
        logger.info(f"  Total jobs found before filtering: {search_stats['total_jobs_found']}")
        logger.info(f"  Unique jobs before location filtering: {len(all_jobs)}")

        # Apply location filtering to ensure only NY, NJ, PA, MA jobs
        filtered_jobs = filter_jobs_by_location(all_jobs, target_states)
        jobs_removed = len(all_jobs) - len(filtered_jobs)

        logger.info(f"JobSpy: Location filtering kept {len(filtered_jobs)}/{len(all_jobs)} jobs")
        if jobs_removed > 0:
            logger.info(f"JobSpy: Location filtering removed {jobs_removed} jobs outside target states")
            # Log some examples of removed locations for debugging
            removed_locations = []
            for job in all_jobs:
                if job not in filtered_jobs and job.location:
                    removed_locations.append(job.location)
            if removed_locations:
                unique_removed = list(set(removed_locations[:5]))  # Show up to 5 examples
                logger.info(f"JobSpy: Example removed locations: {unique_removed}")

        return filtered_jobs

    except Exception as e:
        logger.error(f"JobSpy critical error: {e}")
        logger.exception("Full exception details:")
        return []


def _convert_dataframe_to_jobs(df: pd.DataFrame, source: str) -> List[JobPosting]:
    """Convert JobSpy DataFrame to JobPosting objects"""
    jobs = []

    for _, row in df.iterrows():
        try:
            # Parse date_posted if available
            posted_at: Optional[datetime] = None
            if pd.notna(row.get('date_posted')):
                try:
                    # JobSpy typically returns dates as pandas timestamps
                    if isinstance(row['date_posted'], pd.Timestamp):
                        posted_at = row['date_posted'].to_pydatetime()
                        # Ensure timezone aware
                        if posted_at.tzinfo is None:
                            posted_at = posted_at.replace(tzinfo=timezone.utc)
                except Exception:
                    posted_at = None

            # Extract and clean fields
            title = str(row.get('title', '')).strip()
            company = str(row.get('company', '')).strip()
            url = str(row.get('job_url', '')).strip()
            description = str(row.get('description', '')).strip()
            location = str(row.get('location', '')).strip() if pd.notna(row.get('location')) else None

            # Skip jobs with missing essential data
            if not title or not company or not url:
                continue

            # Combine multiple description fields if available
            full_description = description
            if pd.notna(row.get('job_function')):
                full_description += f" Functions: {row['job_function']}"
            if pd.notna(row.get('benefits')):
                full_description += f" Benefits: {row['benefits']}"

            job = JobPosting(
                title=title,
                company=company,
                url=url,
                description=full_description,
                posted_at=posted_at,
                source=f"{source}_jobspy",
                location=location
            )

            jobs.append(job)

        except Exception as e:
            print(f"JobSpy warning: Failed to parse job row: {e}", file=sys.stderr)
            continue

    return jobs