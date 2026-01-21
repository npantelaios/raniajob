from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Set

from .config import AppConfig, load_config
from .fetcher import Fetcher
from .filters import exclude_keyword_match, filter_by_date, include_keyword_match, normalize_keywords, is_hourly_job, extract_state, extract_salary
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
    days_back: int,
) -> List[JobPosting]:
    now = datetime.now(timezone.utc)
    filtered: List[JobPosting] = []

    # Debugging counters
    filter_stats = {
        'total_input': 0,
        'date_filtered': 0,
        'job_title_filtered': 0,
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
            print(f"DEBUG: Date filtered out: {item.title} (posted: {item.date_posted})", file=sys.stderr)
            continue

        # Job title filtering (only if job_titles is not empty)
        if job_titles and not include_keyword_match(item.title, job_titles):
            filter_stats['job_title_filtered'] += 1
            print(f"DEBUG: Job title filtered out: {item.title}", file=sys.stderr)
            continue

        # Include keyword filtering
        combined_text = f"{item.title} {item.description}"
        if not include_keyword_match(combined_text, include_keywords):
            filter_stats['include_keyword_filtered'] += 1
            print(f"DEBUG: Include keyword filtered out: {item.title} (no match in: {combined_text[:100]}...)", file=sys.stderr)
            continue

        # Exclude keyword filtering
        if not exclude_keyword_match(combined_text, exclude_keywords):
            filter_stats['exclude_keyword_filtered'] += 1
            print(f"DEBUG: Exclude keyword filtered out: {item.title} (excluded term found)", file=sys.stderr)
            continue

        # Hourly job filtering - exclude jobs that pay per hour
        if is_hourly_job(combined_text):
            filter_stats['hourly_filtered'] += 1
            print(f"DEBUG: Hourly job filtered out: {item.title}", file=sys.stderr)
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


def _sort_items(items: Iterable[JobPosting]) -> List[JobPosting]:
    return sorted(items, key=lambda item: item.date_posted or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


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
    """Generate timestamped output paths for filtered and unfiltered results."""
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

    filtered_path = outputs_dir / filtered_filename
    unfiltered_path = outputs_dir / unfiltered_filename

    return str(filtered_path), str(unfiltered_path)


def run_pipeline(config: AppConfig, output_base_name: str, output_format: str, extra_keywords: List[str], send_email: bool = False) -> List[JobPosting]:
    start_time = time.time()

    include_keywords = normalize_keywords(config.include_keywords + extra_keywords)
    exclude_keywords = normalize_keywords(config.exclude_keywords)
    job_titles = normalize_keywords(config.job_titles)
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
    filtered_path, unfiltered_path = _generate_output_paths(output_base_name, output_format)

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
    print(f"Location filtering: kept {len(location_filtered)}/{len(enriched)} jobs from target states (NY, NJ, PA, MA)", file=sys.stderr)

    # Apply other filters (keywords, dates, etc.)
    filtered = _apply_filters(location_filtered, include_keywords, exclude_keywords, job_titles, config.schedule.days_back)
    ordered = _sort_items(filtered)

    # Write filtered results
    if output_format == "json":
        write_json(filtered_path, ordered)
    elif output_format == "csv":
        write_csv(filtered_path, ordered)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    print(f"Wrote {len(ordered)} filtered jobs to: {filtered_path}", file=sys.stderr)

    # Print final stats report
    _print_stats_report(unfiltered_sorted, ordered, unfiltered_path, filtered_path)

    # Send email report if requested
    if send_email:
        send_email_report(unfiltered_sorted, ordered, unfiltered_path, filtered_path)

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
