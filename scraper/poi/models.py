from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class POICategory(StrEnum):
    METRO_STATION = "metro_station"
    TRAM_STOP = "tram_stop"
    BUS_STOP = "bus_stop"
    RAIL_STATION = "rail_station"
    SHOPPING_CENTER = "shopping_center"


@dataclass(slots=True)
class PointOfInterest:
    id: str
    name: str
    lat: float
    lon: float
    category: str
    source: str
    raw_modes: list[str] = field(default_factory=list)
    stop_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class POICollection:
    source: str
    object_type: str
    fetched_at: str
    items: list[PointOfInterest]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "object_type": self.object_type,
            "fetched_at": self.fetched_at,
            "count": len(self.items),
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(slots=True)
class NearestPOIResult:
    poi: PointOfInterest
    distance_meters: float
    walking_distance_meters_estimate: float
    walking_minutes_estimate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "poi": self.poi.to_dict(),
            "distance_meters": self.distance_meters,
            "walking_distance_meters_estimate": self.walking_distance_meters_estimate,
            "walking_minutes_estimate": self.walking_minutes_estimate,
        }
