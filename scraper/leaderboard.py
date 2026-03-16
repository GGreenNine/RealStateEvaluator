from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .analysis_config import ApartmentAnalysisConfig
from .storage import save_json
from .utils import ensure_dir, utcnow_iso


def scored_output_path(scored_dir: Path, input_file: Path) -> Path:
    return scored_dir / f"{input_file.stem}.score.json"


def load_scored_records(scored_dir: Path) -> list[dict[str, Any]]:
    if not scored_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(scored_dir.glob("*.score.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _sort_key(record: dict[str, Any]) -> tuple[float, float, float, float]:
    listing = record.get("listing") or {}
    derived = record.get("derived_fields") or {}
    return (
        -float(record.get("final_total_score") or 0),
        -float((record.get("llm_scores") or {}).get("confidence") or 0),
        float(listing.get("price_total_value") or float("inf")),
        float(derived.get("calculated_price_per_m2") or float("inf")),
    )


def build_leaderboard_rows(
    scored_records: list[dict[str, Any]],
    config: ApartmentAnalysisConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, record in enumerate(sorted(scored_records, key=_sort_key), start=1):
        listing = record.get("listing") or {}
        derived = record.get("derived_fields") or {}
        llm_scores = record.get("llm_scores") or {}
        hard_scores = record.get("hard_scores") or {}
        row = {
            "rank": rank,
            "final_total_score": record.get("final_total_score"),
            "hard_total_score": record.get("hard_total_score"),
            "llm_total_score": record.get("llm_total_score"),
            "listing_id": record.get("listing_id"),
            "address": listing.get("address"),
            "district": listing.get("district"),
            "city": listing.get("city"),
            "price_total_value": listing.get("price_total_value"),
            "area_m2_value": listing.get("area_m2_value"),
            "calculated_price_per_m2": derived.get("calculated_price_per_m2"),
            "building_year": listing.get("building_year"),
            "rooms": derived.get("normalized_rooms") or listing.get("rooms"),
            "room_gate_status": hard_scores.get("room_gate_status"),
            "hard_review_reason": hard_scores.get("review_reason"),
            "floor_score": hard_scores.get("floor_score"),
            "llm_skipped_reason": record.get("llm_skipped_reason"),
            "recommendation": llm_scores.get("recommendation"),
            "confidence": llm_scores.get("confidence"),
            "url": listing.get("url"),
            "summary": llm_scores.get("summary"),
        }
        rows.append({column: row.get(column) for column in config.output.include_columns})
    return rows


def write_leaderboard_outputs(
    run_dir: Path,
    rows: list[dict[str, Any]],
    config: ApartmentAnalysisConfig,
) -> tuple[Path, Path | None]:
    ensure_dir(run_dir)
    csv_path = run_dir / config.paths.leaderboard_csv_name
    json_path = run_dir / config.paths.leaderboard_json_name

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(config.output.include_columns))
        writer.writeheader()
        writer.writerows(rows)

    written_json_path: Path | None = None
    if config.output.also_write_json:
        save_json(
            json_path,
            {
                "generated_at": utcnow_iso(),
                "rows": rows,
            },
        )
        written_json_path = json_path

    return csv_path, written_json_path
