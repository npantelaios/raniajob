from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Iterable, List, Set

from .config import AppConfig, load_config
from .fetcher import Fetcher
from .filters import exclude_keyword_match, filter_by_date, include_keyword_match, normalize_keywords
from .location_filters import filter_jobs_by_location, get_default_target_states
from .models import JobPosting
from .parser import extract_detail_description
from .sites.registry import get_parser
from .storage import write_csv, write_json


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
        'passed_all_filters': 0
    }

    for item in items:
        filter_stats['total_input'] += 1

        # Date filtering
        if not filter_by_date(item.posted_at, days_back, now=now):
            filter_stats['date_filtered'] += 1
            print(f"DEBUG: Date filtered out: {item.title} (posted: {item.posted_at})", file=sys.stderr)
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

        filter_stats['passed_all_filters'] += 1
        filtered.append(item)

    # Log comprehensive filtering statistics
    print(f"\\nFILTER STATISTICS:", file=sys.stderr)
    print(f"  Total input jobs: {filter_stats['total_input']}", file=sys.stderr)
    print(f"  Date filtered: {filter_stats['date_filtered']}", file=sys.stderr)
    print(f"  Job title filtered: {filter_stats['job_title_filtered']}", file=sys.stderr)
    print(f"  Include keyword filtered: {filter_stats['include_keyword_filtered']}", file=sys.stderr)
    print(f"  Exclude keyword filtered: {filter_stats['exclude_keyword_filtered']}", file=sys.stderr)
    print(f"  Passed all filters: {filter_stats['passed_all_filters']}", file=sys.stderr)
    print(f"", file=sys.stderr)

    return filtered


def _sort_items(items: Iterable[JobPosting]) -> List[JobPosting]:
    return sorted(items, key=lambda item: item.posted_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def run_pipeline(config: AppConfig, output_path: str, output_format: str, extra_keywords: List[str]) -> List[JobPosting]:
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
                        posted_at=item.posted_at,
                        source=item.source,
                        location=item.location,
                    )
                )
            parsed_items = enriched_items
        all_items.extend(parsed_items)

    deduped = _dedupe(all_items)

    # Apply location filtering to ensure only NY, NJ, PA, MA jobs
    target_states = get_default_target_states()
    location_filtered = filter_jobs_by_location(deduped, target_states)
    print(f"Location filtering: kept {len(location_filtered)}/{len(deduped)} jobs from target states (NY, NJ, PA, MA)", file=sys.stderr)

    # Apply other filters (keywords, dates, etc.)
    filtered = _apply_filters(location_filtered, include_keywords, exclude_keywords, job_titles, config.schedule.days_back)
    ordered = _sort_items(filtered)

    if output_format == "json":
        write_json(output_path, ordered)
    elif output_format == "csv":
        write_csv(output_path, ordered)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    return ordered


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily job aggregation and filtering.")
    parser.add_argument("--config", required=True, help="Path to YAML config file.")
    parser.add_argument("--output", required=True, help="Output file path.")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format.")
    parser.add_argument("--keyword", action="append", default=[], help="Extra keyword to filter on.")

    args = parser.parse_args()

    app_config = load_config(args.config)
    run_pipeline(app_config, args.output, args.format, args.keyword)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
