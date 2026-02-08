from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

from .config import AppConfig, load_config
from .fetcher import Fetcher
from .filters import exclude_keyword_match, filter_by_date, include_keyword_match, normalize_keywords, is_hourly_job, extract_state, extract_salary, count_keyword_matches
from .location_filters import filter_jobs_by_location, get_default_target_states
from .models import JobPosting
from .parser import extract_detail_description
from .sites.registry import get_parser
from .storage import write_csv, write_json
from .email_report import send_email_report


def _dedupe(items: Iterable[JobPosting]) -> List[JobPosting]:
    seen: Set[str] = set()
    unique: List[JobPosting] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        unique.append(item)
    return unique


def _fetch_site(fetcher: Fetcher, config) -> List[str]:
    pages: List[str] = []
    for url in config.start_urls:
        # Skip empty URLs (used by jobspy/workday/playwright sites)
        if not url or not url.strip():
            continue
        html = fetcher.get(url)
        if html:
            pages.append(html)
    return pages


def _apply_filters(
    items: Iterable[JobPosting],
    include_keywords: List[str],
    exclude_keywords: List[str],
    job_titles: List[str],
    title_must_contain: List[str],
    title_exclude: List[str],
    days_back: int,
) -> List[JobPosting]:
    now = datetime.now(timezone.utc)
    filtered: List[JobPosting] = []

    # Debugging counters
    filter_stats = {
        'total_input': 0,
        'date_filtered': 0,
        'job_title_filtered': 0,
        'title_must_contain_filtered': 0,
        'title_exclude_filtered': 0,
        'include_keyword_filtered': 0,
        'exclude_keyword_filtered': 0,
        'hourly_filtered': 0,
        'passed_all_filters': 0
    }

    for item in items:
        filter_stats['total_input'] += 1

        # Date filtering
        if not filter_by_date(item.date_posted, days_back, now=now):
            filter_stats['date_filtered'] += 1
            continue

        # Combined text for filtering (title + description)
        combined_text = f"{item.title} {item.description}"

        # Job title filtering (only if job_titles is not empty)
        # Checks BOTH title AND description for any matching job title keyword
        if job_titles and not include_keyword_match(combined_text, job_titles):
            filter_stats['job_title_filtered'] += 1
            continue

        # Title must contain filtering - checks TITLE ONLY for required words
        if title_must_contain and not include_keyword_match(item.title, title_must_contain):
            filter_stats['title_must_contain_filtered'] += 1
            continue

        # Title exclude filtering - reject if title contains any excluded word
        if title_exclude and not exclude_keyword_match(item.title, title_exclude):
            filter_stats['title_exclude_filtered'] += 1
            continue

        # Include keyword filtering
        if not include_keyword_match(combined_text, include_keywords):
            filter_stats['include_keyword_filtered'] += 1
            continue

        # Exclude keyword filtering
        if not exclude_keyword_match(combined_text, exclude_keywords):
            filter_stats['exclude_keyword_filtered'] += 1
            continue

        # Hourly job filtering - exclude jobs that pay per hour
        if is_hourly_job(combined_text):
            filter_stats['hourly_filtered'] += 1
            continue

        filter_stats['passed_all_filters'] += 1
        filtered.append(item)

    # Log comprehensive filtering statistics
    print("\nFILTER STATISTICS:", file=sys.stderr)
    print(f"  Total input jobs: {filter_stats['total_input']}", file=sys.stderr)
    print(f"  Date filtered: {filter_stats['date_filtered']}", file=sys.stderr)
    print(f"  Job title filtered: {filter_stats['job_title_filtered']}", file=sys.stderr)
    print(f"  Include keyword filtered: {filter_stats['include_keyword_filtered']}", file=sys.stderr)
    print(f"  Exclude keyword filtered: {filter_stats['exclude_keyword_filtered']}", file=sys.stderr)
    print(f"  Hourly jobs filtered: {filter_stats['hourly_filtered']}", file=sys.stderr)
    print(f"  Passed all filters: {filter_stats['passed_all_filters']}", file=sys.stderr)
    print("", file=sys.stderr)

    return filtered


def _get_date_priority(date_posted: Optional[datetime], now: datetime) -> int:
    """Return sort priority: 0=today, 1=yesterday, 2=2days ago, 3=N/A, 4+=older"""
    if date_posted is None:
        return 3  # N/A after 2 days ago, before older

    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    post_date = date_posted.replace(hour=0, minute=0, second=0, microsecond=0)
    days_diff = (today - post_date).days

    if days_diff == 0:
        return 0  # Today
    elif days_diff == 1:
        return 1  # Yesterday
    elif days_diff == 2:
        return 2  # 2 days ago
    else:
        return 3 + days_diff  # Older dates: 4, 5, 6...


def _get_state_priority(state: Optional[str]) -> int:
    """Return state priority: NY=0, NJ=1, PA=2, MA=3, CA=4, other=5"""
    state_order = {'NY': 0, 'NJ': 1, 'PA': 2, 'MA': 3, 'CA': 4}
    return state_order.get(state.upper(), 5) if state else 5


def _parse_salary_value(salary: Optional[str]) -> Optional[float]:
    """Parse salary string to get the first numeric value.

    Examples:
        "$50,000" -> 50000.0
        "$120K" -> 120000.0
        "$50,000 - $100,000" -> 50000.0 (uses first value)
    """
    if not salary:
        return None

    # Find first number with optional K suffix
    match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*[kK]?', salary)
    if not match:
        return None

    num_str = match.group(1).replace(',', '')
    try:
        value = float(num_str)
        # Check if K suffix follows
        if re.search(r'[\d,]+(?:\.\d+)?\s*[kK]', salary):
            value *= 1000
        return value
    except ValueError:
        return None


def _get_salary_priority(salary: Optional[str]) -> Tuple[int, float]:
    """Return salary priority: (bucket, -value for decreasing sort).

    Bucket 0: salary <= $50,000 (sorted decreasing)
    Bucket 1: N/A (no salary)
    Bucket 2: salary > $50,000 (sorted decreasing)
    """
    value = _parse_salary_value(salary)

    if value is None:
        return (1, 0)  # N/A bucket
    elif value <= 50000:
        return (0, -value)  # Low salary bucket, negative for decreasing
    else:
        return (2, -value)  # High salary bucket, negative for decreasing


def _sort_items(items: Iterable[JobPosting]) -> List[JobPosting]:
    """Sort by date priority, then state priority, then salary priority."""
    now = datetime.now(timezone.utc)
    return sorted(items, key=lambda item: (
        _get_date_priority(item.date_posted, now),
        _get_state_priority(item.state),
        _get_salary_priority(item.salary)
    ))


def _enrich_jobs(items: Iterable[JobPosting]) -> List[JobPosting]:
    """Enrich jobs with state and salary information."""
    enriched: List[JobPosting] = []
    for item in items:
        state = extract_state(item.location)
        salary = extract_salary(item.description)
        enriched.append(
            JobPosting(
                title=item.title,
                company=item.company,
                url=item.url,
                description=item.description,
                date_posted=item.date_posted,
                source=item.source,
                location=item.location,
                state=state,
                salary=salary,
                expiration_date=item.expiration_date,
            )
        )
    return enriched


def _count_by_domain(items: List[JobPosting]) -> dict:
    """Count jobs by URL domain."""
    from urllib.parse import urlparse
    counts: dict = {}
    for item in items:
        try:
            domain = urlparse(item.url).netloc or "unknown"
            if domain.startswith("www."):
                domain = domain[4:]
        except Exception:
            domain = "unknown"
        counts[domain] = counts.get(domain, 0) + 1
    return counts


def _print_stats_report(unfiltered: List[JobPosting], filtered: List[JobPosting], unfiltered_path: str, filtered_path: str) -> None:
    """Print a summary stats report."""
    unfiltered_by_domain = _count_by_domain(unfiltered)
    filtered_by_domain = _count_by_domain(filtered)

    print("\n" + "=" * 60, file=sys.stderr)
    print("                    JOB SCRAPING REPORT", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    print(f"\nUNFILTERED RESULTS: {len(unfiltered)} total jobs", file=sys.stderr)
    print(f"  File: {unfiltered_path}", file=sys.stderr)
    print("  By domain:", file=sys.stderr)
    for domain, count in sorted(unfiltered_by_domain.items(), key=lambda x: -x[1]):
        print(f"    - {domain}: {count} jobs", file=sys.stderr)

    print(f"\nFILTERED RESULTS: {len(filtered)} total jobs", file=sys.stderr)
    print(f"  File: {filtered_path}", file=sys.stderr)
    print("  By domain:", file=sys.stderr)
    for domain, count in sorted(filtered_by_domain.items(), key=lambda x: -x[1]):
        print(f"    - {domain}: {count} jobs", file=sys.stderr)

    print("\n" + "=" * 60, file=sys.stderr)


def _generate_output_paths(base_name: str, output_format: str) -> tuple:
    """Generate timestamped output paths for filtered, unfiltered, and super-filtered results."""
    # Get project root and create outputs directory
    project_root = Path(__file__).parent.parent.parent
    outputs_dir = project_root / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create filenames with timestamp at the end
    ext = f".{output_format}"
    filtered_filename = f"{base_name}_{timestamp}{ext}"
    unfiltered_filename = f"NO_FILTERING_{base_name}_{timestamp}{ext}"
    super_filtered_filename = f"SUPER_FILTERED_{base_name}_{timestamp}{ext}"

    filtered_path = outputs_dir / filtered_filename
    unfiltered_path = outputs_dir / unfiltered_filename
    super_filtered_path = outputs_dir / super_filtered_filename

    return str(filtered_path), str(unfiltered_path), str(super_filtered_path)


def run_pipeline(config: AppConfig, output_base_name: str, output_format: str, extra_keywords: List[str], send_email: bool = False) -> List[JobPosting]:
    start_time = time.time()

    include_keywords = normalize_keywords(config.include_keywords + extra_keywords)
    exclude_keywords = normalize_keywords(config.exclude_keywords)
    job_titles = normalize_keywords(config.job_titles)
    title_must_contain = normalize_keywords(config.title_must_contain)
    title_exclude = normalize_keywords(config.title_exclude)
    fetcher = Fetcher(
        sleep_seconds=config.fetcher.sleep_seconds,
        timeout=config.fetcher.timeout,
        rotate_user_agents=config.fetcher.rotate_user_agents,
        use_cloudscraper=config.fetcher.use_cloudscraper
    )

    all_items: List[JobPosting] = []
    for site in config.sites:
        if not site.enabled:
            continue
        parser = get_parser(site.type)
        pages = _fetch_site(fetcher, site)

        # Pass fetcher to JobSpy parser for HTML date extraction
        if site.type == "jobspy":
            parsed_items = parser(pages, site, site.base_url or "", site.name, fetcher)
        else:
            parsed_items = parser(pages, site, site.base_url or "", site.name)
        if site.detail_page.enabled and site.detail_page.description_selector:
            enriched_items: List[JobPosting] = []
            for item in parsed_items:
                if item.description:
                    enriched_items.append(item)
                    continue
                detail_html = fetcher.get(item.url)
                detail_description = extract_detail_description(detail_html, site.detail_page.description_selector)
                enriched_items.append(
                    JobPosting(
                        title=item.title,
                        company=item.company,
                        url=item.url,
                        description=detail_description,
                        date_posted=item.date_posted,
                        source=item.source,
                        location=item.location,
                        expiration_date=item.expiration_date,
                    )
                )
            parsed_items = enriched_items
        all_items.extend(parsed_items)

    deduped = _dedupe(all_items)

    # Enrich jobs with state and salary information
    enriched = _enrich_jobs(deduped)

    # Generate output paths with timestamps
    filtered_path, unfiltered_path, super_filtered_path = _generate_output_paths(output_base_name, output_format)

    # Write unfiltered results (all enriched items, sorted by date)
    unfiltered_sorted = _sort_items(enriched)
    if output_format == "json":
        write_json(unfiltered_path, unfiltered_sorted)
    elif output_format == "csv":
        write_csv(unfiltered_path, unfiltered_sorted)
    print(f"Wrote {len(unfiltered_sorted)} unfiltered jobs to: {unfiltered_path}", file=sys.stderr)

    # Apply location filtering to ensure only NY, NJ, PA, MA jobs
    target_states = get_default_target_states()
    location_filtered = filter_jobs_by_location(enriched, target_states)
    print(f"Location filtering: kept {len(location_filtered)}/{len(enriched)} jobs from target states (NY, NJ, PA, MA, CA)", file=sys.stderr)

    # Apply other filters (keywords, dates, etc.)
    filtered = _apply_filters(location_filtered, include_keywords, exclude_keywords, job_titles, title_must_contain, title_exclude, config.schedule.days_back)
    ordered = _sort_items(filtered)

    # Write filtered results
    if output_format == "json":
        write_json(filtered_path, ordered)
    elif output_format == "csv":
        write_csv(filtered_path, ordered)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    print(f"Wrote {len(ordered)} filtered jobs to: {filtered_path}", file=sys.stderr)

    # Create super-filtered output (jobs with 2+ keyword matches)
    # Use job_titles for super-filtering (include_keywords is often empty)
    super_filtered = [
        item for item in ordered
        if count_keyword_matches(f"{item.title} {item.description}", job_titles) >= 2
    ]
    super_ordered = _sort_items(super_filtered)
    if output_format == "json":
        write_json(super_filtered_path, super_ordered)
    elif output_format == "csv":
        write_csv(super_filtered_path, super_ordered)
    print(f"Wrote {len(super_ordered)} super-filtered jobs (2+ keyword matches) to: {super_filtered_path}", file=sys.stderr)

    # Print final stats report
    _print_stats_report(unfiltered_sorted, ordered, unfiltered_path, filtered_path)

    # Send email report if requested
    if send_email:
        send_email_report(unfiltered_sorted, ordered, unfiltered_path, filtered_path, super_filtered=super_ordered)

    # Print total run time
    elapsed = time.time() - start_time
    print(f"\n⏱️  Total run time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)", file=sys.stderr)

    return ordered


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily job aggregation and filtering.")
    parser.add_argument("--config", required=True, help="Path to YAML config file.")
    parser.add_argument("--output", default="jobs", help="Base name for output files (without extension). Files will be saved to outputs/ folder with timestamp.")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format.")
    parser.add_argument("--keyword", action="append", default=[], help="Extra keyword to filter on.")
    parser.add_argument("--email", action="store_true", help="Send email report after scraping. Requires GMAIL_ADDRESS, GMAIL_APP_PASSWORD, and REPORT_RECIPIENT environment variables.")

    args = parser.parse_args()

    app_config = load_config(args.config)
    run_pipeline(app_config, args.output, args.format, args.keyword, send_email=args.email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
