from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def _select_first_text(node, selector: Optional[str]) -> str:
    if not selector:
        return ""
    target = node.select_one(selector)
    if not target:
        return ""
    return " ".join(target.get_text(strip=True).split())


def _select_first_attr(node, selector: Optional[str], attr: Optional[str]) -> str:
    if not selector:
        return ""
    target = node.select_one(selector)
    if not target:
        return ""
    if attr:
        return str(target.get(attr, "")).strip()
    return str(target.get("href", "")).strip()


def parse_list_page(html: str, list_item_selector: str):
    soup = BeautifulSoup(html, "html.parser")
    return soup.select(list_item_selector)


def extract_job_fields(node, config, base_url: Optional[str]):
    title = _select_first_text(node, config.title_selector)
    company = _select_first_text(node, config.company_selector) if config.company_selector else ""
    date_raw = _select_first_attr(node, config.date_selector, config.date_attr) if config.date_selector else ""
    url_raw = _select_first_attr(node, config.url_selector, config.url_attr)
    description = _select_first_text(node, config.description_selector) if config.description_selector else ""
    location = _select_first_text(node, config.location_selector) if config.location_selector else ""

    url = urljoin(base_url, url_raw) if base_url else url_raw
    return title, company, date_raw, url, description, location


def extract_detail_description(html: str, selector: Optional[str]) -> str:
    if not selector:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    target = soup.select_one(selector)
    if not target:
        return ""
    return " ".join(target.get_text(strip=True).split())
