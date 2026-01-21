from __future__ import annotations

from typing import Iterable, List

from ..filters import parse_posted_date, extract_all_dates
from ..models import JobPosting
from ..parser import extract_job_fields, parse_list_page


def parse_generic_site(html_pages: Iterable[str], config, base_url: str, source_name: str) -> List[JobPosting]:
    postings: List[JobPosting] = []
    for html in html_pages:
        nodes = parse_list_page(html, config.list_item_selector)
        for node in nodes:
            title, company, date_raw, url, description, location = extract_job_fields(node, config, base_url)
            if not title or not url:
                continue

            # Extract dates from all available text
            all_text = f"{title} {description} {date_raw or ''}"
            date_posted, expiration_date = extract_all_dates(all_text)

            # Fall back to parse_posted_date if extract_all_dates didn't find a posted date
            if not date_posted and date_raw:
                date_posted = parse_posted_date(date_raw)

            postings.append(
                JobPosting(
                    title=title,
                    company=company or "Unknown",
                    url=url,
                    description=description,
                    date_posted=date_posted,
                    source=source_name,
                    location=location or None,
                    expiration_date=expiration_date,
                )
            )
    return postings
