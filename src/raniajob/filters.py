from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

try:
    from dateutil import parser as date_parser
except ImportError:  # pragma: no cover - fallback only if dependency missing
    date_parser = None


_RELATIVE_RE = re.compile(r"(\d+)\s*(day|days|hour|hours|minute|minutes|week|weeks|month|months)\s*ago", re.IGNORECASE)

# Comprehensive date patterns for extraction
_DATE_PATTERNS = [
    # ISO format: 2024-01-15, 2024-01-15T10:30:00
    (re.compile(r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?'), 'iso'),
    # US format: 01/15/2024, 1/15/2024, 01-15-2024
    (re.compile(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}'), 'us'),
    # US short: 01/15/24, 1/15/24
    (re.compile(r'\d{1,2}[/-]\d{1,2}[/-]\d{2}(?!\d)'), 'us_short'),
    # Written: January 15, 2024 or Jan 15, 2024
    (re.compile(r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}', re.IGNORECASE), 'written'),
    # Written EU: 15 Jan 2024, 15 January 2024
    (re.compile(r'\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}', re.IGNORECASE), 'written_eu'),
]
_HOURLY_PAY_RE = re.compile(r"(an\s+hour|per\s+hour|/\s*hour|\$\d+\.?\d*/\s*hr|\$\d+\.?\d*\s*/\s*hour)", re.IGNORECASE)

# Salary pattern - ONLY matches when $ is directly to the left of the number
# Examples: $80,000, $120K, $80,000 - $120,000, $150k-$200k
_SALARY_RE = re.compile(
    r"\$[\d,]+(?:\.\d{2})?\s*[kK]?"  # Must start with $ followed by number
    r"(?:\s*[-–]\s*\$[\d,]+(?:\.\d{2})?\s*[kK]?)?",  # Optional range (also requires $)
    re.IGNORECASE
)

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
        if unit.startswith("week"):
            return now - timedelta(weeks=value)
        if unit.startswith("month"):
            return now - timedelta(days=value * 30)  # Approximate

    if raw.lower() in {"today", "just now"}:
        return now

    if raw.lower() == "yesterday":
        return now - timedelta(days=1)

    if date_parser:
        try:
            parsed = date_parser.parse(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, OverflowError):
            return None

    return None


def classify_date(dt: datetime, now: datetime) -> str:
    """Classify date as 'posted' or 'expiration'.

    Args:
        dt: The date to classify
        now: Current datetime for comparison

    Returns:
        'expiration' if date is more than 1 day in the future, 'posted' otherwise
    """
    if dt > now + timedelta(days=1):
        return 'expiration'
    return 'posted'


def extract_all_dates(text: str, now: Optional[datetime] = None) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Extract date_posted and expiration_date from text.

    Parses various date formats and classifies them:
    - Past/present dates -> date_posted
    - Future dates (>1 day ahead) -> expiration_date

    Args:
        text: Text to extract dates from
        now: Current datetime (defaults to now)

    Returns:
        Tuple of (date_posted, expiration_date)
    """
    if not text:
        return (None, None)

    now = now or datetime.now(timezone.utc)
    dates_found: List[datetime] = []

    # Try relative patterns first (these are always posted dates)
    relative_match = _RELATIVE_RE.search(text)
    if relative_match:
        parsed = parse_posted_date(relative_match.group(0), now)
        if parsed:
            dates_found.append(parsed)

    # Check for today/yesterday
    text_lower = text.lower()
    if "today" in text_lower or "just now" in text_lower:
        dates_found.append(now)
    if "yesterday" in text_lower:
        dates_found.append(now - timedelta(days=1))

    # Try all date patterns
    for pattern, pattern_type in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            date_str = match.group(0)
            parsed = None

            if date_parser:
                try:
                    parsed = date_parser.parse(date_str)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                except (ValueError, OverflowError):
                    continue
            else:
                # Fallback parsing for common formats
                try:
                    if pattern_type == 'iso':
                        if 'T' in date_str:
                            parsed = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        else:
                            parsed = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                except (ValueError, OverflowError):
                    continue

            if parsed:
                dates_found.append(parsed)

    # Classify dates
    date_posted: Optional[datetime] = None
    expiration_date: Optional[datetime] = None

    for dt in dates_found:
        classification = classify_date(dt, now)
        if classification == 'expiration':
            if expiration_date is None or dt < expiration_date:
                expiration_date = dt
        else:
            if date_posted is None or dt > date_posted:
                date_posted = dt

    return (date_posted, expiration_date)


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

    ONLY matches when $ is directly to the left of the number.
    Examples: $80,000, $120K, $80,000 - $120,000

    Will NOT match: 80,000, USD 80000, Salary: 100000
    """
    if not text:
        return None

    match = _SALARY_RE.search(text)
    if match:
        result = match.group(0).strip()
        # Final validation: must contain $
        if '$' in result:
            return result

    return None


def filter_by_date(date_posted: Optional[datetime], days_back: int, now: Optional[datetime] = None, allow_no_date: bool = True) -> bool:
    """Filter jobs by posted date.

    Args:
        date_posted: The posting date of the job
        days_back: Number of days back to allow
        now: Current time (defaults to now)
        allow_no_date: If True, jobs with no date pass the filter (default True)
    """
    if date_posted is None:
        return allow_no_date  # Allow jobs with unknown posting dates
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)
    return date_posted >= cutoff
