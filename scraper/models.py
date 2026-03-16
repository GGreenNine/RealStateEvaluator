from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ListingCard:
    url: str
    listing_id: str | None = None
    address: str | None = None
    price_total: str | None = None
    price_total_raw: str | None = None
    price_total_value: int | None = None
    area_m2: str | None = None
    area_m2_raw: str | None = None
    area_m2_value: float | None = None
    rooms: str | None = None
    seller_name: str | None = None
    meta_raw: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ListingDetails:
    listing_id: str | None
    url: str
    title: str | None = None
    price_total: str | None = None
    price_total_raw: str | None = None
    price_total_value: int | None = None
    price_per_m2: str | None = None
    price_per_m2_raw: str | None = None
    price_per_m2_value: float | None = None
    area_m2: str | None = None
    area_m2_raw: str | None = None
    area_m2_value: float | None = None
    address: str | None = None
    district: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    floor: str | None = None
    floor_raw: str | None = None
    floor_current: int | None = None
    floor_total: int | None = None
    building_year: int | None = None
    listing_overview: str | None = None
    description: str | None = None
    planned_repairs: str | None = None
    completed_repairs: str | None = None
    maintenance_fee: str | None = None
    maintenance_fee_raw: str | None = None
    maintenance_fee_value: float | None = None
    water_fee: str | None = None
    water_fee_raw: str | None = None
    water_fee_value: float | None = None
    sauna_fee: str | None = None
    sauna_fee_raw: str | None = None
    sauna_fee_value: float | None = None
    parking_fee: str | None = None
    parking_fee_raw: str | None = None
    parking_fee_value: float | None = None
    land_ownership_normalized: str | None = None
    land_ownership_raw: str | None = None
    land_ownership: str | None = None
    rooms: str | None = None
    building_type: str | None = None
    seller_name: str | None = None
    nearest_metro_station_id: str | None = None
    nearest_metro_station_name: str | None = None
    nearest_metro_distance_meters: float | None = None
    nearest_metro_walking_minutes: float | None = None
    metro_score: int | None = None
    source_start_url: str | None = None
    scraped_at: str | None = None
    parse_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ListingRecord(ListingDetails):
    new_listing: bool = False
    price_changed: bool = False
    previous_price_total_value: int | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    card: dict[str, Any] | None = None


@dataclass(slots=True)
class StateEntry:
    identity_key: str
    listing_id: str | None
    url: str
    price_total_value: int | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    seen_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScraperState:
    updated_at: str | None = None
    listings: dict[str, StateEntry] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "updated_at": self.updated_at,
            "listings": {
                key: value.to_dict()
                for key, value in sorted(self.listings.items(), key=lambda item: item[0])
            },
        }
