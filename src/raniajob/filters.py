from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

try:
    from dateutil import parser as date_parser
except ImportError:  # pragma: no cover - fallback only if dependency missing
    date_parser = None


_RELATIVE_RE = re.compile(r"(\d+)\s*(day|days|hour|hours|minute|minutes)\s*ago", re.IGNORECASE)


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
