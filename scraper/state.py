from __future__ import annotations

import json
from pathlib import Path

from .models import ListingRecord, ScraperState, StateEntry
from .utils import ensure_parent_dir


def load_state(path: Path) -> ScraperState:
    if not path.exists():
        return ScraperState(updated_at=None, listings={})

    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    listings: dict[str, StateEntry] = {}
    for key, value in raw.get("listings", {}).items():
        listings[key] = StateEntry(
            identity_key=key,
            listing_id=value.get("listing_id"),
            url=value.get("url", ""),
            price_total_value=value.get("price_total_value"),
            first_seen_at=value.get("first_seen_at"),
            last_seen_at=value.get("last_seen_at"),
            seen_count=value.get("seen_count", 0),
        )

    return ScraperState(updated_at=raw.get("updated_at"), listings=listings)


def apply_state(records: list[ListingRecord], state: ScraperState, run_timestamp: str) -> ScraperState:
    updated: dict[str, StateEntry] = dict(state.listings)

    for record in records:
        identity = record.listing_id or record.url
        previous = state.listings.get(identity)

        if previous is None:
            record.new_listing = True
            record.price_changed = False
            record.previous_price_total_value = None
            record.first_seen_at = run_timestamp
            record.last_seen_at = run_timestamp
            updated[identity] = StateEntry(
                identity_key=identity,
                listing_id=record.listing_id,
                url=record.url,
                price_total_value=record.price_total_value,
                first_seen_at=run_timestamp,
                last_seen_at=run_timestamp,
                seen_count=1,
            )
            continue

        record.new_listing = False
        record.previous_price_total_value = previous.price_total_value
        record.price_changed = (
            record.price_total_value is not None
            and previous.price_total_value is not None
            and record.price_total_value != previous.price_total_value
        )
        record.first_seen_at = previous.first_seen_at or run_timestamp
        record.last_seen_at = run_timestamp

        updated[identity] = StateEntry(
            identity_key=identity,
            listing_id=record.listing_id or previous.listing_id,
            url=record.url,
            price_total_value=record.price_total_value
            if record.price_total_value is not None
            else previous.price_total_value,
            first_seen_at=previous.first_seen_at or run_timestamp,
            last_seen_at=run_timestamp,
            seen_count=previous.seen_count + 1,
        )

    return ScraperState(updated_at=run_timestamp, listings=updated)


def save_state(path: Path, state: ScraperState) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as file:
        json.dump(state.to_dict(), file, ensure_ascii=False, indent=2)
