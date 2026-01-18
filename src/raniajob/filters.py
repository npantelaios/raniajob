from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

try:
    from dateutil import parser as date_parser
except ImportError:  # pragma: no cover - fallback only if dependency missing
    date_parser = None


_RELATIVE_RE = re.compile(r"(\d+)\s*(day|days|hour|hours|minute|minutes)\s*ago", re.IGNORECASE)
_HOURLY_PAY_RE = re.compile(r"(an\s+hour|per\s+hour|/\s*hour|\$\d+\.?\d*/\s*hr|\$\d+\.?\d*\s*/\s*hour)", re.IGNORECASE)
_SALARY_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?(?:\s*[-–]\s*\$[\d,]+(?:\.\d{2})?)?(?:\s*(?:per\s+year|/\s*year|annually|/\s*yr|k))?", re.IGNORECASE)

# US State abbreviations for extraction
_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
}

_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC"
}


def normalize_keywords(keywords: Iterable[str]) -> List[str]:
    return [item.strip().lower() for item in keywords if item and item.strip()]


def include_keyword_match(text: str, keywords: Iterable[str]) -> bool:
    if not keywords:
        return True
    haystack = text.lower()
    return any(keyword in haystack for keyword in keywords)


def exclude_keyword_match(text: str, keywords: Iterable[str]) -> bool:
    if not keywords:
        return True
    haystack = text.lower()
    return not any(keyword in haystack for keyword in keywords)


def parse_posted_date(raw: str, now: Optional[datetime] = None) -> Optional[datetime]:
    if not raw:
        return None
    raw = raw.strip()
    now = now or datetime.now(timezone.utc)

    match = _RELATIVE_RE.search(raw)
    if match:
        value = int(match.group(1))
        unit = match.group(2).lower()
        if unit.startswith("day"):
            return now - timedelta(days=value)
        if unit.startswith("hour"):
            return now - timedelta(hours=value)
        if unit.startswith("minute"):
            return now - timedelta(minutes=value)

    if raw.lower() in {"today", "just now"}:
        return now

    if date_parser:
        try:
            parsed = date_parser.parse(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, OverflowError):
            return None

    return None


def is_hourly_job(text: str) -> bool:
    """Check if the job description indicates hourly pay.

    Returns True if the text contains patterns like 'an hour', 'per hour', '/hour', '$XX/hr'
    """
    return bool(_HOURLY_PAY_RE.search(text))


def extract_state(location: Optional[str]) -> Optional[str]:
    """Extract US state abbreviation from a location string.

    Handles formats like:
    - "Boston, MA"
    - "New York, NY"
    - "San Francisco, California"
    - "Massachusetts"
    """
    if not location:
        return None

    location = location.strip()

    # Try to find state abbreviation (e.g., "Boston, MA" or "MA")
    # Look for 2-letter state code, typically after comma or at end
    parts = [p.strip() for p in location.replace(",", " ").split()]
    for part in reversed(parts):  # Check from end first
        upper_part = part.upper()
        if upper_part in _US_STATES:
            return upper_part

    # Try to match full state names
    location_lower = location.lower()
    for state_name, abbrev in _STATE_NAMES.items():
        if state_name in location_lower:
            return abbrev

    return None


def extract_salary(text: str) -> Optional[str]:
    """Extract salary information from job description.

    Looks for patterns like:
    - "$80,000 - $120,000"
    - "$150k"
    - "$50,000 per year"
    - "$100,000/year"
    """
    if not text:
        return None

    match = _SALARY_RE.search(text)
    if match:
        return match.group(0).strip()

    return None


def filter_by_date(posted_at: Optional[datetime], days_back: int, now: Optional[datetime] = None, allow_no_date: bool = True) -> bool:
    """Filter jobs by posted date.

    Args:
        posted_at: The posting date of the job
        days_back: Number of days back to allow
        now: Current time (defaults to now)
        allow_no_date: If True, jobs with no date pass the filter (default True)
    """
    if posted_at is None:
        return allow_no_date  # Allow jobs with unknown posting dates
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)
    return posted_at >= cutoff
