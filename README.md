# raniajob

A configurable job-scraping pipeline that pulls listings from multiple sites, filters by date and keywords, and writes a structured output file.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

Copy `config.example.yaml` and edit selectors per site.

```bash
cp config.example.yaml config.yaml
```

Config knobs you can tweak:
- `sites[].enabled` to turn a source on/off.
- `sites[].max_pages` reserved for pagination (currently only the first page is fetched).
- `job_titles` matches against titles only.
- `include_keywords` / `exclude_keywords` match against title + description.

## Run

```bash
python src/test1.py --config config.yaml --output jobs.json --format json
```

## Notes

- Prefer site APIs or email alerts where available. Scraping may violate some sites' terms.
- Use CSS selectors from browser devtools to tune each site.
- Enable `detail_page` when the listing page does not include the full job description.
- If a site renders jobs via JavaScript, you'll need to swap in a browser automation fetcher (Playwright/Selenium).
- LinkedIn/Indeed should be handled via alerts or APIs; automated scraping risks bans.

## Schedule (optional)

```bash
0 8 * * * /path/to/raniajob/.venv/bin/python /path/to/raniajob/src/test1.py --config /path/to/raniajob/config.yaml --output /path/to/raniajob/jobs.json --format json
```
