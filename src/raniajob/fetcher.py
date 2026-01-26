from __future__ import annotations

import random
import sys
import time
from typing import Dict, List, Optional

import requests


class Fetcher:
    def __init__(
        self,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 20,
        sleep_seconds: float = 0.0,
        rotate_user_agents: bool = True,
        use_cloudscraper: bool = False
    ):
        self._rotate_user_agents = rotate_user_agents
        self._use_cloudscraper = use_cloudscraper

        # Initialize session (cloudscraper or requests)
        if use_cloudscraper:
            try:
                import cloudscraper
                self._session = cloudscraper.create_scraper()
            except ImportError:
                print("Warning: cloudscraper not installed, falling back to requests", file=sys.stderr)
                self._session = requests.Session()
        else:
            self._session = requests.Session()

        # Set default headers
        default_headers = self._get_browser_headers()
        self._session.headers.update(headers or default_headers)

        self._timeout = timeout
        self._sleep_seconds = sleep_seconds
        self._user_agents = self._get_user_agents()

    def _get_user_agents(self) -> List[str]:
        """Get list of realistic user agents for rotation"""
        return [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        ]

    def _get_browser_headers(self) -> Dict[str, str]:
        """Get realistic browser headers"""
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
        }

    def _rotate_headers(self) -> None:
        """Rotate user agent and related headers"""
        if self._rotate_user_agents and self._user_agents:
            user_agent = random.choice(self._user_agents)
            self._session.headers.update({"User-Agent": user_agent})

    def get(self, url: str, silent: bool = False, raise_on_error: bool = False) -> str:
        """Fetch URL content.

        Args:
            url: URL to fetch
            silent: If True, suppress error warnings (useful when errors are expected/handled)
            raise_on_error: If True, raise exception instead of returning empty string

        Returns:
            HTML content or empty string on error (unless raise_on_error=True)
        """
        try:
            # Rotate user agent if enabled
            self._rotate_headers()

            response = self._session.get(url, timeout=self._timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            # Only print warning if not in silent mode
            if not silent:
                print(f"fetch warning: {url} -> {exc}", file=sys.stderr)
            # Re-raise if requested, otherwise return empty string
            if raise_on_error:
                raise
            return ""
        finally:
            if self._sleep_seconds > 0:
                # Add some randomness to sleep time to appear more human-like
                sleep_time = self._sleep_seconds + random.uniform(-0.5, 0.5)
                sleep_time = max(0.1, sleep_time)  # Ensure minimum sleep
                time.sleep(sleep_time)
