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
    poi/
      __init__.py
      distance.py
      models.py
      repository.py
      service.py
      providers/
        __init__.py
        base.py
        digitransit.py
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
    poi/
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

Optional Digitransit environment example:

```powershell
Copy-Item .env.example .env
```

The project reads Digitransit settings from environment variables; `.env.example` is only a reference file and is not loaded automatically.

## How to run

Current CLI supports subcommands, but old scraper usage still works. These are equivalent:

```powershell
python main.py scrape --start-url "https://asunnot.oikotie.fi/..."
python main.py --start-url "https://asunnot.oikotie.fi/..."
```

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

Fetch and store the local metro station dictionary from Digitransit:

```powershell
python main.py fetch-metro-stations --output data/poi/metro_stations.json
```

Fetch tram stops:

```powershell
python main.py fetch-tram-stops --output data/poi/tram_stops.json
```

Fetch rail stations:

```powershell
python main.py fetch-rail-stations --output data/poi/rail_stations.json
```

With an explicit Digitransit subscription key:

```powershell
$env:DIGITRANSIT_SUBSCRIPTION_KEY="your_key"
python main.py fetch-metro-stations
```

## Output files

- `data/listings_latest.json` contains the latest full snapshot.
- `data/runs/<timestamp>/` is created for every scraper run.
- `data/runs/<timestamp>/_run.json` contains the full per-run snapshot.
- `data/runs/<timestamp>/<price> <address>.json` contains one apartment per file.
- `data/state.json` stores cross-run state used to detect new listings and price changes.

All JSON is written in UTF-8 with `ensure_ascii=False` and `indent=2`.

Example:

```text
data/
  listings_latest.json
  runs/
    2026-03-15T20-29-27+00-00/
      _run.json
      189000 Kyyhkysmäki 1 A.json
      158000 Auringonkatu 8 B.json
```

## Local POI data

The scraper now supports a local POI dictionary layer. Metro stations are stored in:

- `data/poi/metro_stations.json`
- `data/poi/tram_stops.json`
- `data/poi/rail_stations.json`

Example structure:

```json
{
  "source": "digitransit_hsl",
  "object_type": "metro_station",
  "fetched_at": "2026-03-16T12:34:56+00:00",
  "count": 17,
  "items": [
    {
      "id": "HSL:1040201",
      "name": "Kamppi",
      "lat": 60.169296,
      "lon": 24.933508,
      "category": "metro_station",
      "source": "digitransit_hsl",
      "raw_modes": [
        "SUBWAY"
      ],
      "stop_ids": [
        "HSL:1040201",
        "HSL:1040202"
      ],
      "metadata": {
        "stop_count": 2
      }
    }
  ]
}
```

The POI layer is intentionally generic. Categories already defined in code:

- `metro_station`
- `tram_stop`
- `bus_stop`
- `rail_station`
- `shopping_center`

Current support:

- `metro_station`: normalized at station level from Digitransit `stations`
- `tram_stop`: normalized at stop level from Digitransit `stops`
- `rail_station`: normalized at station level from Digitransit `stations`

Example `tram_stops.json` entry:

```json
{
  "source": "digitransit_hsl",
  "object_type": "tram_stop",
  "fetched_at": "2026-03-16T12:34:56+00:00",
  "count": 123,
  "items": [
    {
      "id": "HSL:1000102",
      "name": "Lasipalatsi",
      "lat": 60.169,
      "lon": 24.936,
      "category": "tram_stop",
      "source": "digitransit_hsl",
      "raw_modes": [
        "TRAM"
      ],
      "stop_ids": [
        "HSL:1000102"
      ],
      "metadata": {
        "normalization_level": "stop",
        "code": "0102",
        "parent_station_id": "HSL:1000100",
        "parent_station_name": "Lasipalatsi"
      }
    }
  ]
}
```

Example `rail_stations.json` entry:

```json
{
  "source": "digitransit_hsl",
  "object_type": "rail_station",
  "fetched_at": "2026-03-16T12:34:56+00:00",
  "count": 17,
  "items": [
    {
      "id": "HSL:1020553",
      "name": "Pasila",
      "lat": 60.1989,
      "lon": 24.9335,
      "category": "rail_station",
      "source": "digitransit_hsl",
      "raw_modes": [
        "RAIL"
      ],
      "stop_ids": [
        "HSL:1020553",
        "HSL:1020554"
      ],
      "metadata": {
        "normalization_level": "station",
        "stop_count": 2
      }
    }
  ]
}
```

## Metro enrichment

Listing coordinates are parsed from the detail page by looking first in JSON-LD `geo.latitude` / `geo.longitude`, then by falling back to raw HTML pattern matching.

When POI enrichment is enabled and `data/poi/metro_stations.json` exists, each listing gets these extra fields:

- `latitude`
- `longitude`
- `nearest_metro_station_id`
- `nearest_metro_station_name`
- `nearest_metro_distance_meters`
- `nearest_metro_walking_minutes`
- `metro_score`
- `nearest_tram_stop_id`
- `nearest_tram_stop_name`
- `nearest_tram_stop_distance_meters`
- `nearest_tram_stop_walking_minutes`
- `tram_score`
- `nearest_rail_station_id`
- `nearest_rail_station_name`
- `nearest_rail_station_distance_meters`
- `nearest_rail_station_walking_minutes`
- `rail_score`

Walking time is estimated from haversine distance:

- `distance_meters = haversine(lat1, lon1, lat2, lon2)`
- `walking_distance_meters_estimate = distance_meters * walking_detour_factor`
- `walking_minutes_estimate = walking_distance_meters_estimate / walking_speed_m_per_min`

Default enrichment settings:

- `enable_poi_enrichment = true`
- `enable_metro_enrichment = true`
- `enable_tram_enrichment = true`
- `enable_rail_enrichment = true`
- `walking_detour_factor = 1.2`
- `walking_speed_m_per_min = 80`

The metro score is calculated as:

- `minutes < 10` -> `2`
- `10 <= minutes <= 15` -> `1`
- `minutes > 15` -> `0`

The tram score is calculated as:

- `minutes < 5` -> `2`
- `5 <= minutes <= 10` -> `1`
- `minutes > 10` -> `0`

The rail score is calculated as:

- `minutes < 10` -> `2`
- `10 <= minutes <= 20` -> `1`
- `minutes > 20` -> `0`

If coordinates are missing or the metro JSON file does not exist, metro fields stay `null` and the scraper continues.

## Apartment analysis

Apartment analysis is a separate stage from scraping:

- `config/apartment_analysis.yaml` holds hard-score thresholds, output names, and OpenAI settings.
- `prompts/apartment_llm_scoring_prompt.txt` holds the fixed prompt for soft scoring.
- By default, the analysis config uses `gpt-5-mini` to reduce LLM cost for per-listing scoring.
- The LLM payload is reduced by field selection only; selected text fields are preserved in full without truncation.
- By default, the LLM stage runs only for listings with `hard_total_score >= 3`.
- The LLM stage now scores only renovation / building-repair risk. Transit and other objective distance metrics are handled outside the model.

Set the API key in PowerShell:

```powershell
$env:OPENAI_API_KEY="your_api_key"
```

Evaluate one scraped run directory and build the leaderboard:

```powershell
python evaluate_run.py --run-dir "data/runs/2026-03-15T21 15 13+00 00" --build-leaderboard
```

Rebuild the leaderboard later without rescoring:

```powershell
python build_leaderboard.py --run-dir "data/runs/2026-03-15T21 15 13+00 00"
```

Analysis outputs:

- `data/runs/<timestamp>/scored/*.score.json` stores one scored apartment per file.
- `data/runs/<timestamp>/llm_payloads/*.llm-input.json` stores the reduced payload sent to the LLM plus field-length metadata for review.
- `data/runs/<timestamp>/leaderboard.csv` stores the ranking for Excel and Google Sheets.
- `data/runs/<timestamp>/leaderboard.json` stores the same ranking in structured JSON.

### Analysis scoring model

The current model is intentionally biased toward technical safety and transport access, not toward chasing the cheapest `€/m²`.

`final_total_score` is built from:

- `value_score = price_per_m2_score + size_score`
- `technical_risk_score = building_age_score + renovations_score`
- `transit_score = max(metro_score, tram_score, rail_score) + multimodal_bonus`
- `plot_ownership_score`
- `maintenance_fee_score`
- `floor_score`

If a listing is hard-disqualified, `final_total_score = 0`.

Hard scoring uses smooth interpolation instead of only step thresholds:

- `building_age_score` is only a weak baseline prior.
- `price_per_m2_score` is capped at a low weight.
- `size_score` is capped at a low weight and favours roughly `50-65 m²`.
- `maintenance_fee_score` is based on `maintenance_fee_per_m2`, not the absolute monthly fee.

The LLM adds only renovation risk:

- `renovations_score` focuses on plumbing / line renovation, roof, facade, balconies, windows, drainage, and similar major systems.
- For buildings from 1985 or earlier, missing evidence of pipe or line renovation is treated as a strong negative signal.
- Older buildings can still score well if major systems are clearly updated.

Transit is positive-only:

- distant transport does not give negative points
- good access to metro, tram, or rail gives a bonus
- `multimodal_bonus = 0.5` when at least two transport modes are strong

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
- Metro enrichment is optional and driven by local JSON data under `data/poi/`.
- Metro, tram, and rail enrichment all reuse the same `POIRepository` / `POIService` lookup flow.
- To add `bus_stop` later, extend `DigitransitPOIProvider.fetch(...)` for `POICategory.BUS_STOP`, save it through `POIRepository.path_for_category(...)`, and wire one more category entry into the enrichment loop in `scraper/pipeline.py`.
