from __future__ import annotations

from typing import Any, Mapping

from .analysis_config import ApartmentAnalysisConfig


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\xa0", " ").strip()
    if not text:
        return None
    return " ".join(text.split())


def _field_stats(value: str | None) -> dict[str, Any]:
    if value is None:
        return {
            "original_length": 0,
            "output_length": 0,
            "truncated": False,
        }
    return {
        "original_length": len(value),
        "output_length": len(value),
        "truncated": False,
    }


def build_llm_input_payload(
    listing: Mapping[str, Any],
    config: ApartmentAnalysisConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    title = _normalize_text(listing.get("title"))
    address = _normalize_text(listing.get("address"))
    description = _normalize_text(listing.get("description"))
    listing_overview = _normalize_text(listing.get("listing_overview"))
    planned_repairs = _normalize_text(listing.get("planned_repairs"))
    completed_repairs = _normalize_text(listing.get("completed_repairs"))

    payload: dict[str, Any] = {
        "listing_id": listing.get("listing_id"),
        "url": listing.get("url"),
        "title": title,
        "address": address,
        "district": _normalize_text(listing.get("district")),
        "city": _normalize_text(listing.get("city")),
        "listing_overview": listing_overview,
        "description": description,
        "planned_repairs": planned_repairs,
        "completed_repairs": completed_repairs,
    }
    payload = {key: value for key, value in payload.items() if value not in (None, "", [], {})}

    debug_payload = {
        "payload": payload,
        "preserve_full_text": config.llm_input.preserve_full_text,
        "field_stats": {
            "title": _field_stats(title),
            "address": _field_stats(address),
            "listing_overview": _field_stats(listing_overview),
            "description": _field_stats(description),
            "planned_repairs": _field_stats(planned_repairs),
            "completed_repairs": _field_stats(completed_repairs),
        },
    }
    return payload, debug_payload
