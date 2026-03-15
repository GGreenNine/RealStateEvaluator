from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


WHITESPACE_RE = re.compile(r"\s+")
LISTING_ID_RE = re.compile(r"/(\d+)(?:[/?#]|$)")
PAGE_MARKER_RE = re.compile(r"sivu\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Unsupported boolean value: {value}")


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = WHITESPACE_RE.sub(" ", value).strip()
    return cleaned or None


def extract_numeric_string(value: str | None) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    text = text.replace("\xa0", "")
    for token in (
        "\u20ac",
        "EUR",
        "/m\u00b2",
        "/ m\u00b2",
        "m\u00b2",
        "/m2",
        "/ m2",
        "m2",
        "/kk",
        "/ kk",
    ):
        text = text.replace(token, "")
    text = re.sub(r"\b[eE]\b", "", text).strip()
    match = re.search(r"-?[\d\s.,]+", text)
    if not match:
        return None
    return match.group(0).strip()


def normalize_decimal(value: str | None) -> float | None:
    numeric = extract_numeric_string(value)
    if not numeric:
        return None
    compact = numeric.replace(" ", "")
    if "," in compact and "." in compact:
        if compact.rfind(",") > compact.rfind("."):
            compact = compact.replace(".", "").replace(",", ".")
        else:
            compact = compact.replace(",", "")
    elif "," in compact:
        parts = compact.split(",")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            compact = "".join(parts)
        else:
            compact = compact.replace(",", ".")
    else:
        parts = compact.split(".")
        if len(parts) > 2 and all(len(part) == 3 for part in parts[1:]):
            compact = "".join(parts)
        elif len(parts) > 2:
            compact = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(compact)
    except ValueError:
        return None


def normalize_integer(value: str | None) -> int | None:
    decimal = normalize_decimal(value)
    if decimal is None:
        return None
    return int(round(decimal))


def normalize_price(value: str | None) -> int | None:
    return normalize_integer(value)


def normalize_price_per_m2(value: str | None) -> float | None:
    return normalize_decimal(value)


def normalize_area(value: str | None) -> float | None:
    return normalize_decimal(value)


def normalize_monthly_fee(value: str | None) -> float | None:
    return normalize_decimal(value)


def normalize_listing_id(url: str | None) -> str | None:
    if not url:
        return None
    match = LISTING_ID_RE.search(url)
    if match:
        return match.group(1)
    path = urlparse(url).path.rstrip("/")
    if path and path.split("/")[-1].isdigit():
        return path.split("/")[-1]
    return None


def normalize_floor(value: str | None) -> tuple[int | None, int | None]:
    text = normalize_text(value)
    if not text:
        return None, None
    match = re.search(r"(-?\d+)\s*/\s*(-?\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"(-?\d+)", text)
    if match:
        return int(match.group(1)), None
    return None, None


def normalize_land_ownership(value: str | None) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    lowered = text.lower()
    if any(token in lowered for token in ("oma", "owned", "own")):
        return "owned"
    if any(token in lowered for token in ("vuokra", "lease", "leased", "rent")):
        return "leased"
    return "unknown"


def join_non_empty(values: Iterable[str | None], separator: str = ", ") -> str | None:
    cleaned = [normalize_text(value) for value in values if normalize_text(value)]
    if not cleaned:
        return None
    return separator.join(cleaned)
