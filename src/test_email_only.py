#!/usr/bin/env python3
"""Test email report functionality without running the scraper.

Usage:
    python src/test_email_only.py

Requires environment variables:
    - GMAIL_ADDRESS: Your Gmail address
    - GMAIL_APP_PASSWORD: Your Gmail App Password
    - REPORT_RECIPIENTS: Comma-separated list of recipient emails
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from raniajob.models import JobPosting
from raniajob.email_report import send_email_report


def create_test_jobs() -> list[JobPosting]:
    """Create fake test job postings for email testing."""
    now = datetime.now(timezone.utc)

    test_jobs = [
        JobPosting(
            title="Senior Scientist - CRISPR Gene Editing",
            company="Test Pharma Inc",
            url="https://example.com/job/123",
            description="We are seeking a Senior Scientist to lead CRISPR gene editing projects. Requirements: PhD in molecular biology, 5+ years experience.",
            date_posted=now,
            source="test",
            location="Boston, MA",
            state="MA",
            salary="$120,000 - $150,000",
        ),
        JobPosting(
            title="Research Associate - Molecular Biology",
            company="BioTech Solutions",
            url="https://example.com/job/456",
            description="Join our dynamic team as a Research Associate. Focus on molecular biology techniques including PCR, cloning, and protein expression.",
            date_posted=now,
            source="test",
            location="New York, NY",
            state="NY",
            salary="$65,000 - $80,000",
        ),
        JobPosting(
            title="Genomics Data Scientist",
            company="Genomics Corp",
            url="https://example.com/job/789",
            description="Analyze large-scale genomics datasets. Experience with NGS data analysis, Python, and R required.",
            date_posted=now,
            source="test",
            location="Philadelphia, PA",
            state="PA",
            salary="$100,000 - $130,000",
        ),
        JobPosting(
            title="Cell Culture Specialist",
            company="Regenerative Medicine Labs",
            url="https://example.com/job/101",
            description="Maintain and expand stem cell cultures for therapeutic applications. GMP experience preferred.",
            date_posted=now,
            source="test",
            location="Newark, NJ",
            state="NJ",
            salary="$55,000 - $70,000",
        ),
    ]

    return test_jobs


def main() -> int:
    print("=" * 60)
    print("EMAIL TEST - Testing email report without scraping")
    print("=" * 60)

    # Create test jobs
    test_jobs = create_test_jobs()
    print(f"\nCreated {len(test_jobs)} test job postings")

    # For testing, filtered jobs = subset of unfiltered
    unfiltered_jobs = test_jobs
    filtered_jobs = test_jobs[:2]  # Simulate some jobs being filtered out

    print(f"Unfiltered: {len(unfiltered_jobs)} jobs")
    print(f"Filtered: {len(filtered_jobs)} jobs")

    # Use temp paths (the email function creates its own output files)
    unfiltered_path = "/tmp/test_unfiltered.json"
    filtered_path = "/tmp/test_filtered.json"

    print("\nSending email report...")
    success = send_email_report(
        unfiltered_jobs,
        filtered_jobs,
        unfiltered_path,
        filtered_path,
    )

    if success:
        print("\n✅ Email sent successfully! Check your inbox.")
        return 0
    else:
        print("\n❌ Failed to send email. Check credentials and try again.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
