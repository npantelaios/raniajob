#!/usr/bin/env python3
"""Test JobSpy with only ZipRecruiter (no Indeed) to verify it works.

This tests that ZipRecruiter scraping works without the Indeed parameter conflicts.

Usage:
    python src/test_jobspy_noindeed.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class MockSiteConfig:
    """Mock site config for testing."""
    search_terms: List[str]
    locations: List[str]
    job_sites: List[str]
    results_wanted: int = 20
    hours_old: int = 168  # 7 days
    enabled: bool = True
    type: str = "jobspy"
    start_urls: List[str] = field(default_factory=list)
    base_url: str = ""
    name: str = "test"


def test_jobspy_ziprecruiter_only():
    """Test JobSpy with only ZipRecruiter."""
    from raniajob.sites.jobspy import parse_jobspy_sites

    print("=" * 60)
    print("JOBSPY TEST - ZipRecruiter Only (No Indeed)")
    print("=" * 60)

    # Create mock config for ZipRecruiter only
    config = MockSiteConfig(
        search_terms=["biotech scientist", "molecular biology"],
        locations=["Boston, MA", "New York, NY"],
        job_sites=["zip_recruiter"],  # Only ZipRecruiter, no Indeed
        results_wanted=20,
        hours_old=168,
        name="test_ziprecruiter",
    )

    print(f"\nJob Sites: {config.job_sites}")
    print(f"Search Terms: {config.search_terms}")
    print(f"Locations: {config.locations}")
    print(f"Results Wanted: {config.results_wanted}")
    print(f"Hours Old: {config.hours_old}")
    print("\nFetching jobs...")

    # Run the scraper
    jobs = parse_jobspy_sites(
        pages=[],  # Not used for JobSpy
        site_config=config,
        base_url="",
        source="test_ziprecruiter",
    )

    print(f"\n{'=' * 60}")
    print(f"RESULTS: Found {len(jobs)} jobs from ZipRecruiter")
    print("=" * 60)

    if jobs:
        print("\nSample jobs (first 5):")
        for i, job in enumerate(jobs[:5], 1):
            print(f"\n{i}. {job.title}")
            print(f"   Company: {job.company}")
            print(f"   Location: {job.location or 'N/A'}")
            print(f"   URL: {job.url[:80]}...")
        return True
    else:
        print("\n❌ No jobs found from ZipRecruiter.")
        print("   This could be due to rate limiting or location issues.")
        return False


def test_jobspy_indeed_only():
    """Test JobSpy with only Indeed (to compare)."""
    from raniajob.sites.jobspy import parse_jobspy_sites

    print("\n" + "=" * 60)
    print("JOBSPY TEST - Indeed Only (for comparison)")
    print("=" * 60)

    # Create mock config for Indeed only
    config = MockSiteConfig(
        search_terms=["biotech scientist"],
        locations=["Boston, MA"],
        job_sites=["indeed"],  # Only Indeed
        results_wanted=15,
        hours_old=168,
        name="test_indeed",
    )

    print(f"\nJob Sites: {config.job_sites}")
    print(f"Search Terms: {config.search_terms}")
    print(f"Locations: {config.locations}")
    print("\nFetching jobs...")

    # Run the scraper
    jobs = parse_jobspy_sites(
        pages=[],
        site_config=config,
        base_url="",
        source="test_indeed",
    )

    print(f"\n{'=' * 60}")
    print(f"RESULTS: Found {len(jobs)} jobs from Indeed")
    print("=" * 60)

    if jobs:
        print("\nSample jobs (first 3):")
        for i, job in enumerate(jobs[:3], 1):
            print(f"\n{i}. {job.title}")
            print(f"   Company: {job.company}")
            print(f"   Location: {job.location or 'N/A'}")
        return True
    else:
        print("\n❌ No jobs found from Indeed.")
        return False


def test_jobspy_both():
    """Test JobSpy with both Indeed and ZipRecruiter."""
    from raniajob.sites.jobspy import parse_jobspy_sites

    print("\n" + "=" * 60)
    print("JOBSPY TEST - Indeed + ZipRecruiter Together")
    print("=" * 60)

    # Create mock config for both sites
    config = MockSiteConfig(
        search_terms=["biotech scientist"],
        locations=["Boston, MA"],
        job_sites=["indeed", "zip_recruiter"],  # Both sites
        results_wanted=20,
        hours_old=168,
        name="test_both",
    )

    print(f"\nJob Sites: {config.job_sites}")
    print(f"Search Terms: {config.search_terms}")
    print(f"Locations: {config.locations}")
    print("\nFetching jobs...")

    # Run the scraper
    jobs = parse_jobspy_sites(
        pages=[],
        site_config=config,
        base_url="",
        source="test_both",
    )

    print(f"\n{'=' * 60}")
    print(f"RESULTS: Found {len(jobs)} total jobs")
    print("=" * 60)

    # Count by source URL domain
    from collections import Counter
    domains = Counter()
    for job in jobs:
        if "indeed" in job.url.lower():
            domains["Indeed"] += 1
        elif "ziprecruiter" in job.url.lower():
            domains["ZipRecruiter"] += 1
        else:
            domains["Other"] += 1

    print("\nJobs by source:")
    for domain, count in domains.items():
        print(f"  {domain}: {count}")

    return len(jobs) > 0


def main() -> int:
    print("Testing JobSpy with individual sites to identify issues...\n")

    results = {}

    # Test ZipRecruiter only
    results["ZipRecruiter"] = test_jobspy_ziprecruiter_only()

    # Test Indeed only
    results["Indeed"] = test_jobspy_indeed_only()

    # Test both together
    results["Both"] = test_jobspy_both()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {test_name}: {status}")

    if all(results.values()):
        print("\n✅ All JobSpy tests passed!")
        return 0
    elif any(results.values()):
        print("\n⚠️  Some JobSpy tests passed, some failed.")
        return 0
    else:
        print("\n❌ All JobSpy tests failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
