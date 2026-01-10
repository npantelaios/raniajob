from __future__ import annotations

import sys
import time
from typing import Dict, Optional

import requests


class Fetcher:
    def __init__(self, headers: Optional[Dict[str, str]] = None, timeout: int = 20, sleep_seconds: float = 0.0):
        self._session = requests.Session()
        self._session.headers.update(
            headers
            or {
                "User-Agent": "raniajob/0.1 (+https://example.com; contact@example.com)",
                "Accept": "text/html,application/xhtml+xml",
            }
        )
        self._timeout = timeout
        self._sleep_seconds = sleep_seconds

    def get(self, url: str) -> str:
        try:
            response = self._session.get(url, timeout=self._timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            print(f"fetch warning: {url} -> {exc}", file=sys.stderr)
            return ""
        finally:
            if self._sleep_seconds > 0:
                time.sleep(self._sleep_seconds)
