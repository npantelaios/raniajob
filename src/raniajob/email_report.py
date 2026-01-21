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

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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


# PDF writing helper
def _write_jobs_pdf(jobs: List[JobPosting], output_path: str, title: str) -> str:
    """Write job postings to a PDF file and return the file path."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Use landscape orientation for better table fit
    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(LETTER),
        leftMargin=0.5*inch,
        rightMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    styles = getSampleStyleSheet()

    # Create custom style for table cells
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
    )

    elements = []

    elements.append(Paragraph(title, styles["Title"]))
    elements.append(
        Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Total: {len(jobs)} jobs",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.2*inch))

    # Column widths: #, Title, Company, URL, Location, State, Salary, Date Posted, Expiration
    col_widths = [0.3*inch, 1.7*inch, 1.2*inch, 2.3*inch, 1.0*inch, 0.4*inch, 0.9*inch, 0.7*inch, 0.7*inch]

    # Header row
    table_data = [["#", "Title", "Company", "URL", "Location", "State", "Salary", "Posted", "Expires"]]

    # Data rows with text truncation and wrapping
    for idx, job in enumerate(jobs, 1):
        # Truncate long fields
        title_text = job.title[:50] + "..." if len(job.title) > 50 else job.title
        company_text = job.company[:25] + "..." if len(job.company) > 25 else job.company
        url_text = job.url[:45] + "..." if len(job.url) > 45 else job.url
        location_text = (job.location or "N/A")[:20]
        state_text = job.state or "N/A"
        salary_text = (job.salary or "N/A")[:15]
        date_posted_text = job.date_posted.strftime("%m/%d") if job.date_posted else "N/A"
        expiration_text = job.expiration_date.strftime("%m/%d") if job.expiration_date else "N/A"

        table_data.append([
            str(idx),
            Paragraph(title_text, cell_style),
            Paragraph(company_text, cell_style),
            Paragraph(url_text, cell_style),
            Paragraph(location_text, cell_style),
            state_text,
            Paragraph(salary_text, cell_style),
            date_posted_text,
            expiration_text,
        ])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            # Header styling
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3498db")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            # Cell styling
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),  # # column centered
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            # Alternating row colors
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            # Padding
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ])
    )

    elements.append(table)
    doc.build(elements)

    return output_path


def send_email_report(
    unfiltered: List[JobPosting],
    filtered: List[JobPosting],
    unfiltered_path: str,
    filtered_path: str,
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

    filtered_pdf_path = output_dir / f"filtered_jobs_{date_str}.pdf"
    unfiltered_pdf_path = output_dir / f"unfiltered_jobs_{date_str}.pdf"

    # Write CSV files
    _write_jobs_csv(filtered, str(filtered_csv_path))
    _write_jobs_csv(unfiltered, str(unfiltered_csv_path))

    # Write PDF files
    _write_jobs_pdf(filtered, str(filtered_pdf_path), "Filtered Job Results")
    _write_jobs_pdf(unfiltered, str(unfiltered_pdf_path), "Unfiltered Job Results")

    try:
        # Create message with attachments
        msg = MIMEMultipart("mixed")
        msg["Subject"] = (
            f"Job Report - {datetime.now().strftime('%Y-%m-%d')} - {len(filtered)} filtered / {len(unfiltered)} total"
        )
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)

        # Simple text body
        text_content = f"Job scraping report attached.\n\nFiltered: {len(filtered)} jobs\nUnfiltered: {len(unfiltered)} jobs"
        msg.attach(MIMEText(text_content, "plain"))

        # Attach CSV and PDF files
        for path in [
            filtered_csv_path,
            unfiltered_csv_path,
            filtered_pdf_path,
            unfiltered_pdf_path,
        ]:
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
