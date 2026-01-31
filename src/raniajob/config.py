from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError as exc:  # pragma: no cover - runtime safeguard
    raise RuntimeError(
        "Missing dependency 'PyYAML'. Install with: pip install -r requirements.txt"
    ) from exc


@dataclass
class DetailPageConfig:
    enabled: bool
    description_selector: Optional[str]


@dataclass
class SiteConfig:
    name: str
    type: str
    enabled: bool
    base_url: Optional[str]
    start_urls: List[str]
    max_pages: int
    list_item_selector: str
    title_selector: str
    company_selector: Optional[str]
    date_selector: Optional[str]
    date_attr: Optional[str]
    url_selector: str
    url_attr: Optional[str]
    description_selector: Optional[str]
    location_selector: Optional[str]
    detail_page: DetailPageConfig
    # JobSpy-specific fields
    search_terms: Optional[List[str]] = None
    locations: Optional[List[str]] = None
    job_sites: Optional[List[str]] = None
    results_wanted: Optional[int] = None
    hours_old: Optional[int] = None
    # Workday-specific fields
    workday_url: Optional[str] = None
    search_term: Optional[str] = None
    max_results: Optional[int] = None
    # Playwright-specific fields
    career_url: Optional[str] = None
    ats_system: Optional[str] = None


@dataclass
class ScheduleConfig:
    days_back: int
    sleep_seconds: float


@dataclass
class FetcherConfig:
    sleep_seconds: float
    rotate_user_agents: bool
    use_cloudscraper: bool
    timeout: int


@dataclass
class AppConfig:
    schedule: ScheduleConfig
    fetcher: FetcherConfig
    include_keywords: List[str]
    exclude_keywords: List[str]
    job_titles: List[str]
    title_must_contain: List[str]
    sites: List[SiteConfig]


def _require(config: Dict[str, Any], key: str, context: str) -> Any:
    if key not in config:
        raise ValueError(f"Missing required key '{key}' in {context}")
    return config[key]


def _load_detail_page(raw: Dict[str, Any]) -> DetailPageConfig:
    if raw is None:
        return DetailPageConfig(enabled=False, description_selector=None)
    return DetailPageConfig(
        enabled=bool(raw.get("enabled", False)),
        description_selector=raw.get("description_selector"),
    )


def _load_site(raw: Dict[str, Any]) -> SiteConfig:
    site_type = raw.get("type", "generic")

    # For JobSpy, Workday, and Playwright sites, make certain fields optional
    if site_type in ("jobspy", "workday", "playwright"):
        list_item_selector = raw.get("list_item_selector", "")
        title_selector = raw.get("title_selector", "")
        url_selector = raw.get("url_selector", "")
        start_urls = raw.get("start_urls", [""])
    else:
        list_item_selector = _require(raw, "list_item_selector", "site")
        title_selector = _require(raw, "title_selector", "site")
        url_selector = _require(raw, "url_selector", "site")
        start_urls = list(_require(raw, "start_urls", "site"))

    return SiteConfig(
        name=_require(raw, "name", "site"),
        type=site_type,
        enabled=bool(raw.get("enabled", True)),
        base_url=raw.get("base_url"),
        start_urls=start_urls,
        max_pages=int(raw.get("max_pages", 1)),
        list_item_selector=list_item_selector,
        title_selector=title_selector,
        company_selector=raw.get("company_selector"),
        date_selector=raw.get("date_selector"),
        date_attr=raw.get("date_attr"),
        url_selector=url_selector,
        url_attr=raw.get("url_attr"),
        description_selector=raw.get("description_selector"),
        location_selector=raw.get("location_selector"),
        detail_page=_load_detail_page(raw.get("detail_page")),
        # JobSpy-specific configuration
        search_terms=raw.get("search_terms"),
        locations=raw.get("locations"),
        job_sites=raw.get("job_sites"),
        results_wanted=raw.get("results_wanted"),
        hours_old=raw.get("hours_old"),
        # Workday-specific configuration
        workday_url=raw.get("workday_url"),
        search_term=raw.get("search_term"),
        max_results=raw.get("max_results"),
        # Playwright-specific configuration
        career_url=raw.get("career_url"),
        ats_system=raw.get("ats_system"),
    )


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    schedule_raw = raw.get("schedule", {})
    schedule = ScheduleConfig(
        days_back=int(schedule_raw.get("days_back", 1)),
        sleep_seconds=float(schedule_raw.get("sleep_seconds", 0.0)),
    )

    fetcher_raw = raw.get("fetcher", {})
    fetcher = FetcherConfig(
        sleep_seconds=float(fetcher_raw.get("sleep_seconds", schedule.sleep_seconds)),
        rotate_user_agents=bool(fetcher_raw.get("rotate_user_agents", True)),
        use_cloudscraper=bool(fetcher_raw.get("use_cloudscraper", False)),
        timeout=int(fetcher_raw.get("timeout", 20)),
    )

    include_keywords_raw = raw.get("include_keywords", raw.get("keywords", []))
    include_keywords = [str(item).strip() for item in include_keywords_raw if str(item).strip()]
    exclude_keywords = [str(item).strip() for item in raw.get("exclude_keywords", []) if str(item).strip()]
    job_titles = [str(item).strip() for item in raw.get("job_titles", []) if str(item).strip()]
    title_must_contain = [str(item).strip() for item in raw.get("title_must_contain", []) if str(item).strip()]
    sites = [_load_site(item) for item in raw.get("sites", [])]
    if not sites:
        raise ValueError("Config must include at least one site")

    return AppConfig(
        schedule=schedule,
        fetcher=fetcher,
        include_keywords=include_keywords,
        exclude_keywords=exclude_keywords,
        job_titles=job_titles,
        title_must_contain=title_must_contain,
        sites=sites,
    )
