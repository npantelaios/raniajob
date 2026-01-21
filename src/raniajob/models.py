from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class JobPosting:
    title: str
    company: str
    url: str
    description: str
    date_posted: Optional[datetime]
    source: str
    location: Optional[str] = None
    state: Optional[str] = None
    salary: Optional[str] = None
    expiration_date: Optional[datetime] = None
