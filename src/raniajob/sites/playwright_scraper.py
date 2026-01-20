"""Playwright-based scraper for career sites that require JavaScript rendering.

This module handles scraping for companies that don't use Workday:
- Johnson & Johnson (Taleo)
- AstraZeneca (Eightfold AI)
- Novo Nordisk (SAP SuccessFactors)
- Gilead (Yello)
- AbbVie (Attrax)
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import re

from ..models import JobPosting

# Try to import playwright
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print(
        "Warning: Playwright not available. Install with: pip install playwright && playwright install chromium",
        file=sys.stderr,
    )


def parse_playwright_site(
    pages: List[str], site_config, base_url: str, source: str
) -> List[JobPosting]:
    """
    Scrape career sites using Playwright browser automation.

    The 'pages' parameter is ignored - we use the site config directly.
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright not available - install with: pip install playwright && playwright install chromium")
        return []

    career_url = getattr(site_config, "career_url", None)
    if not career_url:
        logger.error(f"No career_url configured for site: {source}")
        return []

    ats_system = getattr(site_config, "ats_system", "unknown")
    search_term = getattr(site_config, "search_term", "scientist")
    max_results = getattr(site_config, "max_results", 100)

    logger.info(f"Playwright: Scraping {source} ({ats_system}) - {career_url}")

    try:
        # Route to appropriate scraper based on ATS system
        if ats_system == "taleo":
            jobs = _scrape_taleo(career_url, search_term, max_results, source, logger)
        elif ats_system == "eightfold":
            jobs = _scrape_eightfold(career_url, search_term, max_results, source, logger)
        elif ats_system == "successfactors":
            jobs = _scrape_successfactors(career_url, search_term, max_results, source, logger)
        elif ats_system == "yello":
            jobs = _scrape_yello(career_url, search_term, max_results, source, logger)
        elif ats_system == "attrax":
            jobs = _scrape_attrax(career_url, search_term, max_results, source, logger)
        else:
            logger.warning(f"Unknown ATS system: {ats_system} - using generic scraper")
            jobs = _scrape_generic(career_url, search_term, max_results, source, logger)

        logger.info(f"Playwright: Found {len(jobs)} jobs from {source}")
        return jobs

    except Exception as e:
        logger.error(f"Playwright: Error scraping {source}: {e}")
        return []


def _scrape_taleo(
    career_url: str,
    search_term: str,
    max_results: int,
    source: str,
    logger: logging.Logger,
) -> List[JobPosting]:
    """Scrape Taleo career sites (J&J)."""
    jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            # Navigate to the careers page
            logger.info(f"Taleo: Navigating to {career_url}")
            page.goto(career_url, wait_until="networkidle", timeout=60000)
            time.sleep(3)  # Wait for dynamic content

            # Try to search for the term
            search_input = page.query_selector('input[type="search"], input[name="q"], input[placeholder*="Search"]')
            if search_input:
                search_input.fill(search_term)
                search_input.press("Enter")
                time.sleep(3)

            # Find job listings
            job_cards = page.query_selector_all('[class*="job"], [class*="listing"], [data-job], article')

            logger.info(f"Taleo: Found {len(job_cards)} job cards")

            for card in job_cards[:max_results]:
                try:
                    title_el = card.query_selector('h2, h3, h4, [class*="title"], a')
                    title = title_el.inner_text().strip() if title_el else None

                    link_el = card.query_selector('a[href]')
                    url = link_el.get_attribute("href") if link_el else None
                    if url and not url.startswith("http"):
                        url = f"https://jobs.jnj.com{url}"

                    location_el = card.query_selector('[class*="location"]')
                    location = location_el.inner_text().strip() if location_el else None

                    if title and url:
                        jobs.append(JobPosting(
                            title=title,
                            company="Johnson & Johnson",
                            url=url,
                            description="",
                            posted_at=datetime.now(timezone.utc),
                            source=f"{source}_taleo",
                            location=location,
                        ))
                except Exception as e:
                    logger.debug(f"Taleo: Error parsing job card: {e}")
                    continue

        except PlaywrightTimeout:
            logger.warning(f"Taleo: Timeout loading {career_url} - skipping")
        except Exception as e:
            logger.error(f"Taleo: Error: {e}")
        finally:
            browser.close()

    return jobs


def _scrape_eightfold(
    career_url: str,
    search_term: str,
    max_results: int,
    source: str,
    logger: logging.Logger,
) -> List[JobPosting]:
    """Scrape Eightfold AI career sites (AstraZeneca)."""
    jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            logger.info(f"Eightfold: Navigating to {career_url}")
            page.goto(career_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)  # Eightfold sites are heavy on JS

            # Try to search
            search_input = page.query_selector('input[type="text"], input[placeholder*="Search"], input[aria-label*="Search"]')
            if search_input:
                search_input.fill(search_term)
                search_input.press("Enter")
                time.sleep(3)

            # Find job listings - Eightfold uses various selectors
            job_cards = page.query_selector_all('[class*="position-card"], [class*="job-card"], [data-test*="job"], li[class*="position"]')

            logger.info(f"Eightfold: Found {len(job_cards)} job cards")

            for card in job_cards[:max_results]:
                try:
                    title_el = card.query_selector('[class*="title"], h3, h4, a')
                    title = title_el.inner_text().strip() if title_el else None

                    link_el = card.query_selector('a[href]')
                    url = link_el.get_attribute("href") if link_el else None
                    if url and not url.startswith("http"):
                        url = f"https://careers.astrazeneca.com{url}"

                    location_el = card.query_selector('[class*="location"]')
                    location = location_el.inner_text().strip() if location_el else None

                    if title and url:
                        jobs.append(JobPosting(
                            title=title,
                            company="AstraZeneca",
                            url=url,
                            description="",
                            posted_at=datetime.now(timezone.utc),
                            source=f"{source}_eightfold",
                            location=location,
                        ))
                except Exception as e:
                    logger.debug(f"Eightfold: Error parsing job card: {e}")
                    continue

        except PlaywrightTimeout:
            logger.warning(f"Eightfold: Timeout loading {career_url} - skipping")
        except Exception as e:
            logger.error(f"Eightfold: Error: {e}")
        finally:
            browser.close()

    return jobs


def _scrape_successfactors(
    career_url: str,
    search_term: str,
    max_results: int,
    source: str,
    logger: logging.Logger,
) -> List[JobPosting]:
    """Scrape SAP SuccessFactors career sites (Novo Nordisk)."""
    jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            logger.info(f"SuccessFactors: Navigating to {career_url}")
            page.goto(career_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)

            # SuccessFactors search
            search_input = page.query_selector('input[type="text"], input[id*="search"], input[name*="keyword"]')
            if search_input:
                search_input.fill(search_term)
                # Look for search button
                search_btn = page.query_selector('button[type="submit"], input[type="submit"], button[class*="search"]')
                if search_btn:
                    search_btn.click()
                else:
                    search_input.press("Enter")
                time.sleep(3)

            # Find job listings
            job_cards = page.query_selector_all('[class*="jobResult"], [class*="job-item"], tr[class*="job"], div[class*="requisition"]')

            logger.info(f"SuccessFactors: Found {len(job_cards)} job cards")

            for card in job_cards[:max_results]:
                try:
                    title_el = card.query_selector('a[class*="title"], [class*="jobTitle"], td a, h3')
                    title = title_el.inner_text().strip() if title_el else None

                    link_el = card.query_selector('a[href]')
                    url = link_el.get_attribute("href") if link_el else None
                    if url and not url.startswith("http"):
                        url = f"https://www.novonordisk.com{url}"

                    location_el = card.query_selector('[class*="location"], td:nth-child(2)')
                    location = location_el.inner_text().strip() if location_el else None

                    if title and url:
                        jobs.append(JobPosting(
                            title=title,
                            company="Novo Nordisk",
                            url=url,
                            description="",
                            posted_at=datetime.now(timezone.utc),
                            source=f"{source}_successfactors",
                            location=location,
                        ))
                except Exception as e:
                    logger.debug(f"SuccessFactors: Error parsing job card: {e}")
                    continue

        except PlaywrightTimeout:
            logger.warning(f"SuccessFactors: Timeout loading {career_url} - skipping")
        except Exception as e:
            logger.error(f"SuccessFactors: Error: {e}")
        finally:
            browser.close()

    return jobs


def _scrape_yello(
    career_url: str,
    search_term: str,
    max_results: int,
    source: str,
    logger: logging.Logger,
) -> List[JobPosting]:
    """Scrape Yello career sites (Gilead)."""
    jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            logger.info(f"Yello: Navigating to {career_url}")
            page.goto(career_url, wait_until="networkidle", timeout=60000)
            time.sleep(3)

            # Search
            search_input = page.query_selector('input[type="search"], input[type="text"], input[placeholder*="Search"]')
            if search_input:
                search_input.fill(search_term)
                search_input.press("Enter")
                time.sleep(3)

            # Find job listings
            job_cards = page.query_selector_all('[class*="job"], [class*="listing"], [class*="card"], article')

            logger.info(f"Yello: Found {len(job_cards)} job cards")

            for card in job_cards[:max_results]:
                try:
                    title_el = card.query_selector('h2, h3, h4, [class*="title"], a')
                    title = title_el.inner_text().strip() if title_el else None

                    link_el = card.query_selector('a[href]')
                    url = link_el.get_attribute("href") if link_el else None
                    if url and not url.startswith("http"):
                        url = f"https://gilead.yello.co{url}"

                    location_el = card.query_selector('[class*="location"]')
                    location = location_el.inner_text().strip() if location_el else None

                    if title and url:
                        jobs.append(JobPosting(
                            title=title,
                            company="Gilead Sciences",
                            url=url,
                            description="",
                            posted_at=datetime.now(timezone.utc),
                            source=f"{source}_yello",
                            location=location,
                        ))
                except Exception as e:
                    logger.debug(f"Yello: Error parsing job card: {e}")
                    continue

        except PlaywrightTimeout:
            logger.warning(f"Yello: Timeout loading {career_url} - skipping")
        except Exception as e:
            logger.error(f"Yello: Error: {e}")
        finally:
            browser.close()

    return jobs


def _scrape_attrax(
    career_url: str,
    search_term: str,
    max_results: int,
    source: str,
    logger: logging.Logger,
) -> List[JobPosting]:
    """Scrape Attrax career sites (AbbVie)."""
    jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            logger.info(f"Attrax: Navigating to {career_url}")
            page.goto(career_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)

            # Search
            search_input = page.query_selector('input[type="text"], input[id*="search"], input[name*="keyword"]')
            if search_input:
                search_input.fill(search_term)
                search_input.press("Enter")
                time.sleep(3)

            # Find job listings
            job_cards = page.query_selector_all('[class*="job"], [class*="vacancy"], [class*="listing"], article, li[class*="result"]')

            logger.info(f"Attrax: Found {len(job_cards)} job cards")

            for card in job_cards[:max_results]:
                try:
                    title_el = card.query_selector('h2, h3, h4, [class*="title"], a[class*="job"]')
                    title = title_el.inner_text().strip() if title_el else None

                    link_el = card.query_selector('a[href]')
                    url = link_el.get_attribute("href") if link_el else None
                    if url and not url.startswith("http"):
                        url = f"https://careers.abbvie.com{url}"

                    location_el = card.query_selector('[class*="location"]')
                    location = location_el.inner_text().strip() if location_el else None

                    if title and url:
                        jobs.append(JobPosting(
                            title=title,
                            company="AbbVie",
                            url=url,
                            description="",
                            posted_at=datetime.now(timezone.utc),
                            source=f"{source}_attrax",
                            location=location,
                        ))
                except Exception as e:
                    logger.debug(f"Attrax: Error parsing job card: {e}")
                    continue

        except PlaywrightTimeout:
            logger.warning(f"Attrax: Timeout loading {career_url} - skipping")
        except Exception as e:
            logger.error(f"Attrax: Error: {e}")
        finally:
            browser.close()

    return jobs


def _scrape_generic(
    career_url: str,
    search_term: str,
    max_results: int,
    source: str,
    logger: logging.Logger,
) -> List[JobPosting]:
    """Generic Playwright scraper for unknown ATS systems."""
    jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            logger.info(f"Generic: Navigating to {career_url}")
            page.goto(career_url, wait_until="networkidle", timeout=60000)
            time.sleep(3)

            # Try to find job listings with common selectors
            selectors = [
                '[class*="job"]',
                '[class*="listing"]',
                '[class*="vacancy"]',
                '[class*="position"]',
                'article',
                'li[class*="result"]',
            ]

            job_cards = []
            for selector in selectors:
                cards = page.query_selector_all(selector)
                if cards:
                    job_cards = cards
                    break

            logger.info(f"Generic: Found {len(job_cards)} potential job cards")

            for card in job_cards[:max_results]:
                try:
                    title_el = card.query_selector('h2, h3, h4, [class*="title"], a')
                    title = title_el.inner_text().strip() if title_el else None

                    link_el = card.query_selector('a[href]')
                    url = link_el.get_attribute("href") if link_el else None

                    location_el = card.query_selector('[class*="location"]')
                    location = location_el.inner_text().strip() if location_el else None

                    if title and url:
                        jobs.append(JobPosting(
                            title=title,
                            company=source.replace("_careers", "").replace("_", " ").title(),
                            url=url,
                            description="",
                            posted_at=datetime.now(timezone.utc),
                            source=f"{source}_playwright",
                            location=location,
                        ))
                except Exception as e:
                    logger.debug(f"Generic: Error parsing job card: {e}")
                    continue

        except PlaywrightTimeout:
            logger.warning(f"Generic: Timeout loading {career_url} - skipping")
        except Exception as e:
            logger.error(f"Generic: Error: {e}")
        finally:
            browser.close()

    return jobs
