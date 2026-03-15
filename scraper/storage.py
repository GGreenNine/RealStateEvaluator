from __future__ import annotations

import json
import re
from pathlib import Path

from .utils import ensure_dir, ensure_parent_dir


def save_json(path: Path, payload: dict) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def save_history_snapshot(history_dir: Path, payload: dict) -> Path:
    ensure_dir(history_dir)
    started_at = str(payload["run"]["started_at"]).replace(":", "-")
    file_path = history_dir / f"{started_at}.json"
    with file_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return file_path


def save_text(path: Path, text: str) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as file:
        file.write(text)


WINDOWS_RESERVED_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE_RE = re.compile(r"\s+")


def _sanitize_filename_part(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        text = fallback
    text = text.replace("\xa0", " ")
    text = WINDOWS_RESERVED_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text).strip(" .")
    return text or fallback


def _build_listing_filename(record: dict, index: int) -> str:
    price = record.get("price_total_value") or record.get("price_total") or "unknown-price"
    address = (
        record.get("address")
        or record.get("title")
        or record.get("url")
        or f"listing-{index:03d}"
    )
    price_part = _sanitize_filename_part(str(price), "unknown-price")
    address_part = _sanitize_filename_part(str(address), f"listing-{index:03d}")
    return f"{price_part} {address_part}.json"


def save_run_listing_files(history_dir: Path, payload: dict) -> Path:
    ensure_dir(history_dir)
    started_at = _sanitize_filename_part(str(payload["run"]["started_at"]), "run")
    run_dir = history_dir / started_at
    ensure_dir(run_dir)

    run_summary_path = run_dir / "_run.json"
    save_json(run_summary_path, payload)

    used_names: set[str] = set()
    for index, record in enumerate(payload.get("records", []), start=1):
        filename = _build_listing_filename(record, index)
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        candidate = filename
        counter = 2
        while candidate.casefold() in used_names:
            candidate = f"{stem} ({counter}){suffix}"
            counter += 1
        used_names.add(candidate.casefold())
        save_json(run_dir / candidate, record)

    return run_dir
