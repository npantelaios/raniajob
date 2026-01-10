from __future__ import annotations

import csv
import json
from typing import Iterable, List

from .models import JobPosting


def _as_dict(item: JobPosting) -> dict:
    return {
        "title": item.title,
        "company": item.company,
        "url": item.url,
        "description": item.description,
        "posted_at": item.posted_at.isoformat() if item.posted_at else "",
        "source": item.source,
    }


def write_json(path: str, items: Iterable[JobPosting]) -> None:
    payload = [_as_dict(item) for item in items]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)


def write_csv(path: str, items: Iterable[JobPosting]) -> None:
    rows: List[dict] = [_as_dict(item) for item in items]
    fieldnames = ["title", "company", "url", "description", "posted_at", "source"]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
