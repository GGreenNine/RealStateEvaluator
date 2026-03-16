# Apartment Analysis Feature Plan

## Goal

Add a separate apartment analysis pipeline on top of scraping:

1. read scraped apartment JSON files
2. compute deterministic hard scores in code
3. call OpenAI API for non-deterministic LLM scores
4. merge both score groups into a final score
5. build a ranked leaderboard

This feature should stay independent from scraping so it can be rerun without re-scraping.

## Chosen output format

Primary leaderboard output: CSV

Why CSV:
- easy to open in Excel and Google Sheets
- simple to sort and filter
- easy to diff in git if needed
- trivial to generate from Python

Secondary output: JSON

Why JSON:
- keeps full structured score breakdown
- useful for audits and later LLM comparison

## Feature split

### Hard scoring in code

These criteria should be computed in Python, not by the LLM:

- room count gate
- building year threshold
- plot ownership
- price per square meter
- size score

Reason:
- deterministic
- cheap
- easy to test
- no hallucination risk

### LLM scoring through OpenAI API

These criteria should be scored by the model:

- renovations risk
- metro proximity estimate
- nearby amenities estimate
- commute estimate
- confidence
- recommendation
- concise natural-language summary

Reason:
- requires interpretation from text
- may require soft inference from district and description

## Required files

### Configuration

`config/apartment_analysis.yaml`

Purpose:
- model configuration
- scoring weights
- thresholds
- output file names
- skip and rerun policy

### Prompt

`prompts/apartment_llm_scoring_prompt.txt`

Purpose:
- fixed prompt for LLM scoring
- strict JSON schema
- prevents prompt drift

## Suggested code structure

### New modules

1. `scraper/analysis_config.py`
- load and validate `config/apartment_analysis.yaml`

2. `scraper/analysis_models.py`
- dataclasses or typed dicts for:
  - hard score result
  - llm score result
  - merged apartment score
  - leaderboard row

3. `scraper/hard_scoring.py`
- pure deterministic scoring functions
- no API calls
- easy unit tests

4. `scraper/llm_scoring.py`
- OpenAI API client wrapper
- prompt loading
- structured JSON validation
- retry and parse protection

5. `scraper/leaderboard.py`
- sort results
- write CSV
- write JSON

### New scripts

1. `evaluate_run.py`
- input: one run directory
- reads apartment JSON files
- skips `_run.json`
- computes hard scores
- calls OpenAI API
- writes one scored JSON per apartment

2. `build_leaderboard.py`
- input: one run directory
- reads all scored JSON files
- sorts by final score descending
- writes leaderboard CSV and leaderboard JSON

## Run directory layout

For a run directory like:

`data/runs/2026-03-15T21 15 13+00 00/`

Add:

```text
data/runs/<run_timestamp>/
  _run.json
  160000 Vallikaivanto 3 A, Vallikallio, Espoo.json
  scored/
    160000 Vallikaivanto 3 A, Vallikallio, Espoo.score.json
  leaderboard.csv
  leaderboard.json
```

## Exact scoring flow

### Step 1. Read input apartment JSON

Ignore:
- `_run.json`

Reject or flag if:
- `parse_error` is not null and config says to reject
- `listing_id` and `url` are both missing

### Step 2. Normalize input for analysis

Prepare derived deterministic fields:

- `normalized_rooms`
- `calculated_price_per_m2`
  - use `price_per_m2_value` if present
  - otherwise calculate `price_total_value / area_m2_value`
- `input_hash`
  - hash of fields that affect scoring

Also fix known bad parsed values where possible.
Example from current sample:
- `floor` and `floor_current` are clearly wrong because they contain the price value
- this should not participate in scoring until parser is corrected

### Step 3. Compute hard score

Suggested formula:

- `room_gate`
  - if rooms < min_rooms, mark disqualified
  - final score becomes 0

- `building_age_score`
  - `+3` if `building_year >= 1994`

- `plot_ownership_score`
  - `+2` if `land_ownership_normalized == "owned"`

- `price_per_m2_score`
  - `+3` if `calculated_price_per_m2 <= 3000`

- `size_score`
  - `+1` if `area_m2_value >= 46`
  - `+0.5` for every full additional 10 m2
  - cap using config

Output:
- per-criterion hard scores
- `hard_total_score`
- `disqualified`
- `disqualification_reason`

### Step 4. Call OpenAI API

Only for non-disqualified listings.

Input to model:
- the apartment JSON
- optional derived helper fields that code calculated
  - `calculated_price_per_m2`
  - `normalized_rooms`

Model returns:
- `renovations_score`
- `metro_proximity_score`
- `amenities_score`
- `commute_score`
- `llm_total_score`
- `confidence`
- `recommendation`
- `summary`
- `reasoning_notes`
- `derived_assumptions`

Validation rules:
- valid JSON only
- all required keys present
- all score fields numeric and within configured ranges
- `llm_total_score` must equal sum of LLM criterion scores

If invalid:
- retry up to N times
- on final failure save `llm_error`
- optionally set LLM scores to 0

### Step 5. Merge scores

Final formula:

- if disqualified:
  - `final_total_score = 0`
- else:
  - `final_total_score = hard_total_score + llm_total_score`

Save merged output per apartment in `scored/`.

### Step 6. Build leaderboard

Sort by:

1. `final_total_score` descending
2. `confidence` descending
3. `price_total_value` ascending
4. `calculated_price_per_m2` ascending

Write:

- `leaderboard.csv`
- `leaderboard.json`

## Suggested scored file schema

Each scored apartment file should contain:

```json
{
  "listing_id": "24377023",
  "input_file": "160000 Vallikaivanto 3 A, Vallikallio, Espoo.json",
  "input_hash": "sha256...",
  "prompt_version": "apartment_llm_scoring_prompt_v1",
  "model": "gpt-5",
  "hard_scores": {
    "room_gate_passed": true,
    "building_age_score": 0,
    "plot_ownership_score": 2,
    "price_per_m2_score": 3,
    "size_score": 1.5,
    "hard_total_score": 6.5
  },
  "llm_scores": {
    "renovations_score": 2,
    "metro_proximity_score": 1,
    "amenities_score": 2,
    "commute_score": 1,
    "llm_total_score": 6,
    "confidence": 0.62,
    "recommendation": "review",
    "summary": "Reasonable fundamentals, but location convenience is uncertain.",
    "reasoning_notes": [
      "Planned repairs look moderate rather than severe.",
      "Metro access is not clear from the listing."
    ]
  },
  "final_total_score": 12.5,
  "disqualified": false,
  "disqualification_reason": null,
  "evaluated_at": "2026-03-15T22:00:00+00:00"
}
```

## Exact implementation order

1. Add config loader for `config/apartment_analysis.yaml`
2. Add prompt loader for `prompts/apartment_llm_scoring_prompt.txt`
3. Implement deterministic helpers:
   - room parsing
   - price per m2 calculation
   - input hash generation
4. Implement hard scoring module
5. Implement OpenAI API wrapper
6. Implement strict LLM response validation
7. Implement `evaluate_run.py`
8. Implement `build_leaderboard.py`
9. Add unit tests for hard scoring
10. Add one end-to-end dry run on an existing `data/runs/...` folder

## Things that were missing and should be included

### 1. Input hash and skip logic

Without this, you will re-score unchanged apartments every run and waste tokens.

### 2. Prompt version

Without this, you will not know which score came from which prompt revision.

### 3. Confidence

Location inference is uncertain. Confidence should be stored for filtering and tie-breaking.

### 4. Retry and validation

LLM output must be schema-validated and retried on malformed JSON.

### 5. Parser quality guard

The current sample shows parser corruption in floor fields.
Analysis should not trust obviously bad parsed values blindly.

### 6. Primary and secondary outputs

CSV is best for ranking and review.
JSON is best for audit and future reprocessing.

### 7. Cost control

Only score:
- new listings
- changed listings
- listings without an existing valid score file

## Recommendation

Implement the feature as a local Python pipeline, not as a workflow tool.

That gives:
- reproducible logic
- easier debugging
- full control over scoring and caching
- no dependency on third-party workflow orchestration
