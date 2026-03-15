from __future__ import annotations

import json
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
