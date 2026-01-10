from __future__ import annotations

from typing import Iterable, List

from ..filters import parse_posted_date
from ..models import JobPosting
from ..parser import extract_job_fields, parse_list_page


def parse_generic_site(html_pages: Iterable[str], config, base_url: str, source_name: str) -> List[JobPosting]:
    postings: List[JobPosting] = []
    for html in html_pages:
        nodes = parse_list_page(html, config.list_item_selector)
        for node in nodes:
            title, company, date_raw, url, description = extract_job_fields(node, config, base_url)
            if not title or not url:
                continue
            posted_at = parse_posted_date(date_raw)
            postings.append(
                JobPosting(
                    title=title,
                    company=company or "Unknown",
                    url=url,
                    description=description,
                    posted_at=posted_at,
                    source=source_name,
                )
            )
    return postings
