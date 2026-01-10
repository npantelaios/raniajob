from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Iterable, List, Set

from .config import AppConfig, load_config
from .fetcher import Fetcher
from .filters import exclude_keyword_match, filter_by_date, include_keyword_match, normalize_keywords
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
    for item in items:
        if not filter_by_date(item.posted_at, days_back, now=now):
            continue
        if job_titles and not include_keyword_match(item.title, job_titles):
            continue
        combined_text = f"{item.title} {item.description}"
        if not include_keyword_match(combined_text, include_keywords):
            continue
        if not exclude_keyword_match(combined_text, exclude_keywords):
            continue
        filtered.append(item)
    return filtered


def _sort_items(items: Iterable[JobPosting]) -> List[JobPosting]:
    return sorted(items, key=lambda item: item.posted_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def run_pipeline(config: AppConfig, output_path: str, output_format: str, extra_keywords: List[str]) -> List[JobPosting]:
    include_keywords = normalize_keywords(config.include_keywords + extra_keywords)
    exclude_keywords = normalize_keywords(config.exclude_keywords)
    job_titles = normalize_keywords(config.job_titles)
    fetcher = Fetcher(sleep_seconds=config.schedule.sleep_seconds)

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
                    )
                )
            parsed_items = enriched_items
        all_items.extend(parsed_items)

    deduped = _dedupe(all_items)
    filtered = _apply_filters(deduped, include_keywords, exclude_keywords, job_titles, config.schedule.days_back)
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
