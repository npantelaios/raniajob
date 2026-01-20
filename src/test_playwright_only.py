#!/usr/bin/env python3
"""Test Playwright scrapers for non-Workday companies.

Usage:
    python src/test_playwright_only.py

Requires:
    pip install playwright
    playwright install chromium
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class MockSiteConfig:
    """Mock site config for testing."""
    career_url: str
    ats_system: str
    search_term: str = "scientist"
    max_results: int = 20
    enabled: bool = True
    type: str = "playwright"
    start_urls: List[str] = None
    base_url: str = ""
    name: str = "test"

    def __post_init__(self):
        if self.start_urls is None:
            self.start_urls = []


# Non-Workday companies to test
NON_WORKDAY_COMPANIES = {
    "jnj": {
        "career_url": "https://jobs.jnj.com/en/jobs",
        "ats_system": "taleo",
        "company_name": "Johnson & Johnson",
    },
    "astrazeneca": {
        "career_url": "https://careers.astrazeneca.com/search-jobs",
        "ats_system": "eightfold",
        "company_name": "AstraZeneca",
    },
    "novonordisk": {
        "career_url": "https://www.novonordisk.com/careers/find-a-job.html",
        "ats_system": "successfactors",
        "company_name": "Novo Nordisk",
    },
    "gilead": {
        "career_url": "https://gilead.yello.co/jobs",
        "ats_system": "yello",
        "company_name": "Gilead Sciences",
    },
    "abbvie": {
        "career_url": "https://careers.abbvie.com/en/search-jobs",
        "ats_system": "attrax",
        "company_name": "AbbVie",
    },
}


def test_single_company(company_key: str) -> bool:
    """Test a single non-Workday company."""
    from raniajob.sites.playwright_scraper import parse_playwright_site

    company = NON_WORKDAY_COMPANIES[company_key]

    print(f"\nTesting {company['company_name']} ({company['ats_system']})...")
    print(f"  URL: {company['career_url']}")

    config = MockSiteConfig(
        career_url=company["career_url"],
        ats_system=company["ats_system"],
        search_term="scientist",
        max_results=10,
        name=f"{company_key}_careers",
    )

    jobs = parse_playwright_site(
        pages=[],
        site_config=config,
        base_url=company["career_url"],
        source=f"{company_key}_careers",
    )

    print(f"  Found: {len(jobs)} jobs")

    if jobs:
        print(f"  Sample: {jobs[0].title[:50]}...")
        return True
    return False


def test_all_companies():
    """Test all non-Workday companies."""
    print("=" * 60)
    print("PLAYWRIGHT TEST - Non-Workday Companies (5 total)")
    print("=" * 60)

    results = {}
    for company_key in NON_WORKDAY_COMPANIES:
        try:
            results[company_key] = test_single_company(company_key)
        except Exception as e:
            print(f"  ERROR: {e}")
            results[company_key] = False

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)

    success_count = sum(1 for v in results.values() if v)
    print(f"Successful: {success_count}/{len(results)}")

    for company_key, success in results.items():
        status = "✅" if success else "❌"
        company_name = NON_WORKDAY_COMPANIES[company_key]["company_name"]
        print(f"  {status} {company_name}")

    return success_count > 0


def main() -> int:
    # Check if playwright is available
    try:
        from playwright.sync_api import sync_playwright
        print("Playwright is installed.")
    except ImportError:
        print("ERROR: Playwright not installed.")
        print("Install with: pip install playwright && playwright install chromium")
        return 1

    success = test_all_companies()

    if success:
        print("\n✅ At least one Playwright scraper is working!")
        return 0
    else:
        print("\n❌ All Playwright scrapers failed.")
        print("This may be due to anti-bot protection or site changes.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
