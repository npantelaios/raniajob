"""Email reporting module for job scraping results."""

from __future__ import annotations

import csv
import os
import smtplib
import sys
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional

from .models import JobPosting


def _write_jobs_csv(jobs: List[JobPosting], output_path: str) -> str:
    """Write job postings to a CSV file and return the file path."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["#", "Title", "Company", "URL", "Location", "State", "Salary", "Date Posted", "Expiration Date"])
        for idx, job in enumerate(jobs, 1):
            date_posted_str = job.date_posted.strftime("%Y-%m-%d") if job.date_posted else "N/A"
            expiration_str = job.expiration_date.strftime("%Y-%m-%d") if job.expiration_date else "N/A"
            writer.writerow(
                [
                    idx,
                    job.title,
                    job.company,
                    job.url,
                    job.location or "N/A",
                    job.state or "N/A",
                    job.salary or "N/A",
                    date_posted_str,
                    expiration_str,
                ]
            )
    return output_path


def send_email_report(
    unfiltered: List[JobPosting],
    filtered: List[JobPosting],
    unfiltered_path: str,
    filtered_path: str,
    super_filtered: Optional[List[JobPosting]] = None,
    recipient_emails: Optional[List[str]] = None,
    sender_email: Optional[str] = None,
    app_password: Optional[str] = None,
) -> bool:
    """Send an email report with job scraping results.

    Credentials can be provided as arguments or via environment variables:
    - GMAIL_ADDRESS: Your Gmail address
    - GMAIL_APP_PASSWORD: Your Gmail App Password
    - REPORT_RECIPIENTS: Comma-separated list of email addresses to send report to

    Args:
        super_filtered: Optional list of super-filtered jobs (2+ keyword matches)
        recipient_emails: List of recipient email addresses (overrides env var)
    """
    # Get credentials from environment or arguments
    sender = sender_email or os.environ.get("GMAIL_ADDRESS")
    password = app_password or os.environ.get("GMAIL_APP_PASSWORD")

    # Get recipients - support multiple via comma-separated env var or list argument
    if recipient_emails:
        recipients = recipient_emails
    else:
        recipients_str = os.environ.get("REPORT_RECIPIENTS", "")
        recipients = [
            email.strip() for email in recipients_str.split(",") if email.strip()
        ]

    if not sender or not password:
        print(
            "Email error: Missing credentials. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD environment variables.",
            file=sys.stderr,
        )
        return False

    if not recipients:
        print(
            "Email error: No recipients specified. Set REPORT_RECIPIENTS environment variable (comma-separated for multiple).",
            file=sys.stderr,
        )
        return False

    # Prepare output directory and file paths
    output_dir = Path("outputs_csv_format")
    date_str = datetime.now().strftime("%Y%m%d")

    filtered_csv_path = output_dir / f"filtered_jobs_{date_str}.csv"
    unfiltered_csv_path = output_dir / f"unfiltered_jobs_{date_str}.csv"
    super_filtered_csv_path = output_dir / f"super_filtered_jobs_{date_str}.csv"

    # Write CSV files
    _write_jobs_csv(filtered, str(filtered_csv_path))
    _write_jobs_csv(unfiltered, str(unfiltered_csv_path))
    if super_filtered:
        _write_jobs_csv(super_filtered, str(super_filtered_csv_path))

    try:
        # Create message with attachments
        msg = MIMEMultipart("mixed")
        super_count = len(super_filtered) if super_filtered else 0
        msg["Subject"] = (
            f"Job Report - {datetime.now().strftime('%Y-%m-%d')} - {super_count} super / {len(filtered)} filtered / {len(unfiltered)} total"
        )
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)

        # Simple text body
        text_content = f"Job scraping report attached.\n\nSuper-filtered (2+ keywords): {super_count} jobs\nFiltered: {len(filtered)} jobs\nUnfiltered: {len(unfiltered)} jobs"
        msg.attach(MIMEText(text_content, "plain"))

        # Attach CSV files (super_filtered first)
        attachments = []
        if super_filtered:
            attachments.append(super_filtered_csv_path)
        attachments.extend([filtered_csv_path, unfiltered_csv_path])

        for path in attachments:
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition", f'attachment; filename="{path.name}"'
            )
            msg.attach(part)

        # Send email via Gmail SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())

        print(
            f"✉️  Email report sent successfully to: {', '.join(recipients)}",
            file=sys.stderr,
        )
        return True

    except Exception as e:
        print(f"Email error: Failed to send report: {e}", file=sys.stderr)
        return False
