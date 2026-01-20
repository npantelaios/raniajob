#!/usr/bin/env python3
"""Test Workday scraper with a single company (Pfizer).

Usage:
    python src/test_workday_only.py
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
    workday_url: str
    search_term: Optional[str] = None
    max_results: int = 50
    enabled: bool = True
    type: str = "workday"
    start_urls: List[str] = None
    base_url: str = ""
    name: str = "test"

    def __post_init__(self):
        if self.start_urls is None:
            self.start_urls = []


def test_workday_pfizer():
    """Test the Workday scraper with Pfizer careers."""
    from raniajob.sites.workday import parse_workday_site

    print("=" * 60)
    print("WORKDAY TEST - Testing Pfizer Careers")
    print("=" * 60)

    # Create mock config for Pfizer
    config = MockSiteConfig(
        workday_url="https://pfizer.wd1.myworkdayjobs.com/PfizerCareers",
        search_term="scientist",  # Optional: search for scientist roles
        max_results=10000,  # No limit - get all jobs
        name="pfizer_careers",
    )

    print(f"\nWorkday URL: {config.workday_url}")
    print(f"Search term: {config.search_term}")
    print(f"Max results: {config.max_results}")
    print("\nFetching jobs...")

    # Run the scraper
    jobs = parse_workday_site(
        pages=[],  # Not used for Workday
        site_config=config,
        base_url=config.workday_url,
        source="pfizer_careers",
    )

    print(f"\n{'=' * 60}")
    print(f"RESULTS: Found {len(jobs)} jobs")
    print("=" * 60)

    if jobs:
        print("\nSample jobs (first 5):")
        for i, job in enumerate(jobs[:5], 1):
            print(f"\n{i}. {job.title}")
            print(f"   Company: {job.company}")
            print(f"   Location: {job.location or 'N/A'}")
            print(f"   URL: {job.url[:80]}...")
            if job.posted_at:
                print(f"   Posted: {job.posted_at.strftime('%Y-%m-%d')}")
        return True
    else:
        print("\n❌ No jobs found. The Workday API may have changed or there's a connection issue.")
        return False


def test_workday_multiple():
    """Test the Workday scraper with multiple companies."""
    from raniajob.sites.workday import parse_workday_site, WORKDAY_PHARMA_URLS

    print("\n" + "=" * 60)
    print("WORKDAY TEST - Testing Multiple Companies (12 total)")
    print("=" * 60)

    results = {}
    failed = []

    for company, url in WORKDAY_PHARMA_URLS.items():
        print(f"\nTesting {company.upper()}...")

        config = MockSiteConfig(
            workday_url=url,
            search_term="scientist",
            max_results=10000,  # No limit - get all jobs
            name=f"{company}_careers",
        )

        jobs = parse_workday_site(
            pages=[],
            site_config=config,
            base_url=url,
            source=f"{company}_careers",
        )

        results[company] = len(jobs)
        if len(jobs) == 0:
            failed.append(company)
        print(f"  {company}: {len(jobs)} jobs found")

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    total = sum(results.values())
    print(f"Total jobs found across {len(results)} companies: {total}")
    print(f"Successful: {len(results) - len(failed)}/{len(results)}")
    if failed:
        print(f"Failed companies: {', '.join(failed)}")
    for company, count in results.items():
        status = "✅" if count > 0 else "❌"
        print(f"  {status} {company}: {count} jobs")

    return total > 0


def main() -> int:
    # Test single company first
    success1 = test_workday_pfizer()

    # Optionally test multiple companies
    print("\n" + "-" * 60)
    success2 = test_workday_multiple()

    if success1 or success2:
        print("\n✅ Workday scraper is working!")
        return 0
    else:
        print("\n❌ Workday scraper tests failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
