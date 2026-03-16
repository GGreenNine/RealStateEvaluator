from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..storage import load_json, save_json
from .models import POICategory, POICollection, PointOfInterest


DEFAULT_CATEGORY_FILENAMES: dict[POICategory, str] = {
    POICategory.METRO_STATION: "metro_stations.json",
    POICategory.TRAM_STOP: "tram_stops.json",
    POICategory.BUS_STOP: "bus_stops.json",
    POICategory.RAIL_STATION: "rail_stations.json",
    POICategory.SHOPPING_CENTER: "shopping_centers.json",
}


@dataclass(slots=True)
class POIRepository:
    base_dir: Path

    def path_for_category(self, category: POICategory) -> Path:
        return self.base_dir / DEFAULT_CATEGORY_FILENAMES[category]

    def save_collection(self, collection: POICollection, path: Path | None = None) -> Path:
        target = path or self.path_for_category(POICategory(collection.object_type))
        save_json(target, collection.to_dict())
        return target

    def load_collection(self, path: Path) -> POICollection | None:
        if not path.exists():
            return None
        payload = load_json(path)
        items = [
            PointOfInterest(
                id=str(item["id"]),
                name=str(item["name"]),
                lat=float(item["lat"]),
                lon=float(item["lon"]),
                category=str(item["category"]),
                source=str(item.get("source") or payload.get("source") or ""),
                raw_modes=[str(mode) for mode in item.get("raw_modes", [])],
                stop_ids=[str(stop_id) for stop_id in item.get("stop_ids", [])],
                metadata=dict(item.get("metadata") or {}),
            )
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ]
        return POICollection(
            source=str(payload.get("source") or ""),
            object_type=str(payload.get("object_type") or ""),
            fetched_at=str(payload.get("fetched_at") or ""),
            items=items,
        )
