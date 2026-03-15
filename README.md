# Oikotie Apartment Scraper

Python project for scraping apartment sale listings from Oikotie, saving structured JSON snapshots, and tracking new listings and price changes across runs.

## Project structure

```text
project_root/
  main.py
  requirements.txt
  README.md
  scraper/
    __init__.py
    browser_fallback.py
    client.py
    config.py
    models.py
    pagination.py
    parsers.py
    pipeline.py
    state.py
    storage.py
    utils.py
  data/
    .gitkeep
```

## Libraries

Base dependencies:

- `requests`
- `beautifulsoup4`
- `lxml`

Optional dependency for browser fallback:

- `playwright`

## Installation

### Windows setup

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Optional Playwright fallback:

```powershell
pip install playwright
python -m playwright install chromium
```

## How to run

Scan up to 30 pages:

```powershell
python main.py --start-url "https://asunnot.oikotie.fi/myytavat-asunnot?pagination=1&locations=%5B%5B39,6,%22Espoo%22%5D%5D&cardType=100&buildingType%5B%5D=1&buildingType%5B%5D=256&price%5Bmin%5D=150000&price%5Bmax%5D=250000&size%5Bmin%5D=48" --max-pages 30
```

Scan all pages until the end:

```powershell
python main.py --start-url "https://asunnot.oikotie.fi/myytavat-asunnot?pagination=1&locations=%5B%5B39,6,%22Espoo%22%5D%5D&cardType=100&buildingType%5B%5D=1&buildingType%5B%5D=256&price%5Bmin%5D=150000&price%5Bmax%5D=250000&size%5Bmin%5D=48" --all-pages
```

Use browser fallback:

```powershell
python main.py --start-url "https://asunnot.oikotie.fi/myytavat-asunnot?pagination=1&locations=%5B%5B39,6,%22Espoo%22%5D%5D&cardType=100&buildingType%5B%5D=1&buildingType%5B%5D=256&price%5Bmin%5D=150000&price%5Bmax%5D=250000&size%5Bmin%5D=48" --all-pages --browser-fallback
```

Tune delay, timeout and output paths:

```powershell
python main.py --start-url "https://asunnot.oikotie.fi/myytavat-asunnot?pagination=1&locations=%5B%5B39,6,%22Espoo%22%5D%5D&cardType=100&buildingType%5B%5D=1&buildingType%5B%5D=256&price%5Bmin%5D=150000&price%5Bmax%5D=250000&size%5Bmin%5D=48" --max-pages 20 --delay 1.5 --timeout 25 --output data/listings_latest.json --state-file data/state.json
```

## Output files

- `data/listings_latest.json` contains the latest full snapshot.
- `data/runs/<timestamp>.json` contains a per-run historical snapshot.
- `data/state.json` stores cross-run state used to detect new listings and price changes.

All JSON is written in UTF-8 with `ensure_ascii=False` and `indent=2`.

## How state works

State is stored in `data/state.json` as a dictionary keyed by `listing_id` when available, otherwise by URL.

For each listing, the state keeps:

- `listing_id`
- `url`
- `price_total_value`
- `first_seen_at`
- `last_seen_at`
- `seen_count`

On a new run:

1. The scraper loads the previous state.
2. Each scraped listing is matched by `listing_id` or URL.
3. If no previous entry exists, `new_listing=true`.
4. If the listing exists and `price_total_value` changed, `price_changed=true` and `previous_price_total_value` is filled.
5. `first_seen_at` is preserved from the first run, `last_seen_at` is updated on every successful run.
6. After a successful run, the state file is overwritten with the updated snapshot.

If the scraper is interrupted with `Ctrl+C`, it saves partial output snapshots but does not overwrite `state.json`.

## Browser fallback

Default mode uses `requests` and BeautifulSoup only. If that HTML does not contain the required elements, `--browser-fallback` allows the scraper to retry the same page with Playwright.

The Playwright adapter:

- launches headless Chromium,
- waits for the page to stabilize,
- tries to dismiss common consent or modal buttons,
- returns the final HTML back to the same parsers.

Playwright is optional and is imported lazily, so base mode works without browser dependencies.

## Selectors and parser maintenance

All main selectors and field mappings live in `scraper/parsers.py`:

- `CARD_SELECTORS`
- `DETAIL_SELECTORS`
- `LABEL_FALLBACKS`

If Oikotie changes layout, update those mappings first. The parser strategy is layered:

1. exact CSS selectors,
2. `data-name` field extraction,
3. label-based fallback search,
4. JSON-LD fallback,
5. safe `None` return if nothing matches.

That keeps layout changes isolated to one file instead of spreading selector logic across the whole project.

## Notes

- No database is used.
- No async code is used.
- Logging goes to console.
- One failed page or listing does not stop the whole run unless `--stop-on-error true` is passed.
