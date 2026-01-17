"""Email reporting module for job scraping results."""
from __future__ import annotations

import os
import smtplib
import sys
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .models import JobPosting


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or "unknown"
    except Exception:
        return "unknown"


def _group_by_domain(items: List[JobPosting]) -> Dict[str, List[JobPosting]]:
    """Group jobs by their URL domain."""
    grouped: Dict[str, List[JobPosting]] = defaultdict(list)
    for item in items:
        domain = _extract_domain(item.url)
        grouped[domain].append(item)
    return dict(grouped)


def _count_by_source(items: List[JobPosting]) -> dict:
    """Count jobs by source."""
    counts: dict = {}
    for item in items:
        source = item.source or "unknown"
        counts[source] = counts.get(source, 0) + 1
    return counts


def _count_by_domain(items: List[JobPosting]) -> dict:
    """Count jobs by domain."""
    counts: dict = {}
    for item in items:
        domain = _extract_domain(item.url)
        counts[domain] = counts.get(domain, 0) + 1
    return counts


def generate_report_html(
    unfiltered: List[JobPosting],
    filtered: List[JobPosting],
    unfiltered_path: str,
    filtered_path: str
) -> str:
    """Generate an HTML report of job scraping results, grouped by domain."""
    unfiltered_by_domain = _count_by_domain(unfiltered)
    filtered_by_domain = _count_by_domain(filtered)
    filtered_grouped = _group_by_domain(filtered)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
            h2 {{ color: #34495e; }}
            h3 {{ color: #2980b9; margin-top: 30px; border-left: 4px solid #3498db; padding-left: 10px; }}
            .stats-box {{ background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #3498db; }}
            .domain-section {{ background: #fff; margin: 20px 0; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; }}
            .domain-header {{ background: #3498db; color: white; padding: 10px 15px; border-radius: 5px; margin-bottom: 15px; }}
            .domain-header span {{ font-size: 14px; opacity: 0.9; }}
            .source-list {{ margin-left: 20px; }}
            .source-item {{ margin: 5px 0; }}
            .count {{ font-weight: bold; color: #2980b9; }}
            .file-path {{ font-size: 12px; color: #7f8c8d; word-break: break-all; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            th {{ background-color: #ecf0f1; color: #2c3e50; font-weight: 600; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            tr:hover {{ background-color: #f1f1f1; }}
            .job-title {{ font-weight: bold; color: #2c3e50; }}
            .job-title a {{ color: #3498db; text-decoration: none; }}
            .job-title a:hover {{ text-decoration: underline; }}
            .job-company {{ color: #27ae60; font-weight: 500; }}
            .job-location {{ color: #7f8c8d; }}
            .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
            .summary-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; }}
            .summary-card.green {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }}
            .summary-card h4 {{ margin: 0; font-size: 14px; opacity: 0.9; }}
            .summary-card .number {{ font-size: 36px; font-weight: bold; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔬 Job Scraping Report</h1>
            <p>Generated: {timestamp}</p>

            <div class="summary-grid">
                <div class="summary-card">
                    <h4>Unfiltered Jobs</h4>
                    <div class="number">{len(unfiltered)}</div>
                </div>
                <div class="summary-card green">
                    <h4>Filtered Jobs</h4>
                    <div class="number">{len(filtered)}</div>
                </div>
            </div>

            <div class="stats-box">
                <h2>📊 Unfiltered Results by Domain</h2>
                <p class="file-path">File: {unfiltered_path}</p>
                <div class="source-list">
    """

    for domain, count in sorted(unfiltered_by_domain.items(), key=lambda x: -x[1]):
        html += f'<div class="source-item">• <strong>{domain}</strong>: <span class="count">{count}</span> jobs</div>'

    html += f"""
                </div>
            </div>

            <div class="stats-box">
                <h2>✅ Filtered Results by Domain</h2>
                <p class="file-path">File: {filtered_path}</p>
                <div class="source-list">
    """

    for domain, count in sorted(filtered_by_domain.items(), key=lambda x: -x[1]):
        html += f'<div class="source-item">• <strong>{domain}</strong>: <span class="count">{count}</span> jobs</div>'

    html += """
                </div>
            </div>

            <h2>📋 Jobs by Domain</h2>
    """

    # Generate sections for each domain
    for domain, jobs in sorted(filtered_grouped.items(), key=lambda x: -len(x[1])):
        html += f"""
            <div class="domain-section">
                <div class="domain-header">
                    <strong>{domain}</strong> <span>({len(jobs)} jobs)</span>
                </div>
                <table>
                    <tr>
                        <th>Title</th>
                        <th>Company</th>
                        <th>Location</th>
                    </tr>
        """

        # Show up to 15 jobs per domain
        for job in jobs[:15]:
            title_display = job.title[:70] + "..." if len(job.title) > 70 else job.title
            html += f"""
                    <tr>
                        <td class="job-title"><a href="{job.url}" target="_blank">{title_display}</a></td>
                        <td class="job-company">{job.company}</td>
                        <td class="job-location">{job.location or 'N/A'}</td>
                    </tr>
            """

        if len(jobs) > 15:
            html += f"""
                    <tr>
                        <td colspan="3" style="text-align: center; color: #7f8c8d;">
                            ... and {len(jobs) - 15} more jobs from {domain}
                        </td>
                    </tr>
            """

        html += """
                </table>
            </div>
        """

    html += """
            <p style="color: #7f8c8d; font-size: 12px; margin-top: 30px; text-align: center;">
                This report was automatically generated by the RaniaJob scraper.
            </p>
        </div>
    </body>
    </html>
    """

    return html


def send_email_report(
    unfiltered: List[JobPosting],
    filtered: List[JobPosting],
    unfiltered_path: str,
    filtered_path: str,
    recipient_emails: Optional[List[str]] = None,
    sender_email: Optional[str] = None,
    app_password: Optional[str] = None
) -> bool:
    """Send an email report with job scraping results.

    Credentials can be provided as arguments or via environment variables:
    - GMAIL_ADDRESS: Your Gmail address
    - GMAIL_APP_PASSWORD: Your Gmail App Password
    - REPORT_RECIPIENTS: Comma-separated list of email addresses to send report to

    Args:
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
        recipients = [email.strip() for email in recipients_str.split(",") if email.strip()]

    if not sender or not password:
        print("Email error: Missing credentials. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD environment variables.", file=sys.stderr)
        return False

    if not recipients:
        print("Email error: No recipients specified. Set REPORT_RECIPIENTS environment variable (comma-separated for multiple).", file=sys.stderr)
        return False

    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔬 Job Scraping Report - {datetime.now().strftime('%Y-%m-%d')} - {len(filtered)} jobs found"
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)

        # Generate HTML report
        html_content = generate_report_html(unfiltered, filtered, unfiltered_path, filtered_path)

        # Group by domain for text version
        filtered_by_domain = _count_by_domain(filtered)

        # Create plain text version
        text_content = f"""
Job Scraping Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

UNFILTERED RESULTS: {len(unfiltered)} total jobs
File: {unfiltered_path}

FILTERED RESULTS: {len(filtered)} total jobs
File: {filtered_path}

Jobs by Domain:
"""
        for domain, count in sorted(filtered_by_domain.items(), key=lambda x: -x[1]):
            text_content += f"  - {domain}: {count} jobs\n"

        text_content += "\nTop 10 jobs:\n"
        for i, job in enumerate(filtered[:10], 1):
            text_content += f"{i}. {job.title} at {job.company} ({job.location})\n   URL: {job.url}\n"

        # Attach parts
        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        # Send email via Gmail SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())

        print(f"✉️  Email report sent successfully to: {', '.join(recipients)}", file=sys.stderr)
        return True

    except Exception as e:
        print(f"Email error: Failed to send report: {e}", file=sys.stderr)
        return False
