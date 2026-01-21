# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**raniajob** is a configurable job-scraping pipeline for biotechnology and life sciences positions. It fetches job listings from multiple sites, applies keyword filtering, and outputs structured data in JSON or CSV format.

## Commands

### Setup & Run
```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the scraper
python src/main.py --config config.yaml --output jobs.json --format json

# Run with additional keywords
python src/main.py --config config.yaml --output jobs.json --format json --keyword "synthetic biology" --keyword "automation"
```

### Testing
Currently no test framework is configured. When implementing tests, check for pytest or unittest setup first.

## Architecture

### Pipeline Flow
1. **Configuration** (`config.py`): Reads YAML config with site definitions, keywords, filtering rules
2. **Fetching** (`fetcher.py`): HTTP client with rate limiting and anti-bot headers
3. **Parsing** (`sites/generic.py`): CSS selector-based extraction
4. **Detail Enrichment**: Optional second fetch for job descriptions
5. **Filtering** (`filters.py`): Date, title, and keyword filtering
6. **Deduplication & Sorting**: By URL, then by posted date
7. **Storage** (`storage.py`): JSON or CSV output

### Key Files
- **Entry Point**: `src/main.py` → `raniajob/run.py:main()`
- **Site Config**: Each site in `config.yaml` needs CSS selectors and `enabled` flag
- **Parser Registry**: `sites/registry.py` maps site types to parser functions

## Anti-Bot Implementation

### Current Status
- **No APIs Available**: BioSpace, Work in Biotech, MassBio, HireLifeScience, F6S, biotech-careers.org have no free public APIs
- **Scraping Required**: Must use web scraping with proper anti-detection measures

### Anti-Detection Features Implemented
1. **Realistic Headers**: Browser-like User-Agent and Accept headers
2. **Cookie Management**: Session persistence across requests
3. **Rate Limiting**: Configurable delays between requests
4. **User-Agent Rotation**: Multiple browsers to avoid fingerprinting
5. **Cloudflare Bypass**: Optional cloudscraper integration

### Configuration Options
```yaml
fetcher:
  sleep_seconds: 2.0
  use_cloudscraper: false
  rotate_user_agents: true
  session_cookies: true
```

## JobSpy Integration

**JobSpy** is now integrated as an alternative to site-specific scraping. It searches multiple major job boards simultaneously.

### JobSpy Configuration
```yaml
- name: jobspy_biotech
  type: jobspy
  enabled: true
  search_terms:
    - "CRISPR scientist"
    - "molecular biology"
    - "biotech scientist"
  locations:
    - "Boston, MA"
    - "San Francisco, CA"
  job_sites:
    - "indeed"
    - "glassdoor"
    - "zip_recruiter"
  results_wanted: 30
  hours_old: 72
```

### Benefits
- **Multi-site Search**: Searches Indeed, Glassdoor, ZipRecruiter simultaneously
- **Built-in Anti-Bot**: Uses tls-client for better success rates
- **Rich Data**: Returns salary, company info, job functions
- **No CSS Selectors**: No need to maintain site-specific selectors

### Limitations
- LinkedIn rate limits quickly (~10 pages)
- Glassdoor may have location parsing issues
- Results subject to normal keyword filtering

### Usage Tips
- Use broader search terms than CSS scraping
- Combine with traditional scraping for maximum coverage
- JobSpy works well for major US job boards

## Alternative Libraries

If further alternatives needed:
- **JobFunnel**: Aggregates jobs into spreadsheet with deduplication
- **cloudscraper**: Cloudflare anti-bot bypass

## Notes

- This is for personal, non-commercial use with minimal data collection
- Sites with JavaScript rendering need browser automation (Playwright/Selenium)
- Always respect robots.txt and rate limits
- The pipeline currently fetches only the first page (`max_pages: 1`)