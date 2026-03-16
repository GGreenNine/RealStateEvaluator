from __future__ import annotations

import logging
from pathlib import Path

from .distance import (
    estimate_walking_distance_meters,
    estimate_walking_minutes,
    haversine_distance_meters,
)
from .models import NearestPOIResult, POICategory, PointOfInterest
from .repository import POIRepository

LOGGER = logging.getLogger(__name__)
DEFAULT_METRO_WALKING_SCORE_BANDS: tuple[
    tuple[float | None, float | None, int, bool, bool],
    ...,
] = (
    (None, 10.0, 2, True, False),
    (10.0, 15.0, 1, True, True),
    (15.0, 30.0, 0, False, True),
    (30.0, None, -1, False, True),
)


def score_distance_to_poi(
    minutes: float | None,
    score_bands: tuple[tuple[float | None, float | None, int, bool, bool], ...],
) -> int | None:
    if minutes is None:
        return None
    for min_minutes, max_minutes, score, min_inclusive, max_inclusive in score_bands:
        if min_minutes is None:
            lower_ok = True
        elif min_inclusive:
            lower_ok = minutes >= min_minutes
        else:
            lower_ok = minutes > min_minutes

        if max_minutes is None:
            upper_ok = True
        elif max_inclusive:
            upper_ok = minutes <= max_minutes
        else:
            upper_ok = minutes < max_minutes

        if lower_ok and upper_ok:
            return score
    return None


def score_metro_walking_minutes(minutes: float | None) -> int | None:
    return score_distance_to_poi(minutes, DEFAULT_METRO_WALKING_SCORE_BANDS)


class POIService:
    def __init__(
        self,
        repository: POIRepository,
        walking_detour_factor: float,
        walking_speed_m_per_min: float,
    ) -> None:
        self.repository = repository
        self.walking_detour_factor = walking_detour_factor
        self.walking_speed_m_per_min = walking_speed_m_per_min
        self._collection_cache: dict[tuple[str, str], list[PointOfInterest]] = {}
        self._missing_path_warnings: set[str] = set()

    def load_points(self, category: POICategory, path: Path) -> list[PointOfInterest]:
        cache_key = (str(path.resolve()), category.value)
        if cache_key in self._collection_cache:
            return self._collection_cache[cache_key]

        collection = self.repository.load_collection(path)
        if collection is None:
            if cache_key[0] not in self._missing_path_warnings:
                LOGGER.warning("POI data file not found: %s", path)
                self._missing_path_warnings.add(cache_key[0])
            self._collection_cache[cache_key] = []
            return []

        points = [item for item in collection.items if item.category == category.value]
        self._collection_cache[cache_key] = points
        return points

    def find_nearest_poi(
        self,
        lat: float | None,
        lon: float | None,
        category: POICategory,
        path: Path,
    ) -> NearestPOIResult | None:
        if lat is None or lon is None:
            return None

        points = self.load_points(category, path)
        if not points:
            return None

        nearest: PointOfInterest | None = None
        nearest_distance: float | None = None
        for point in points:
            distance = haversine_distance_meters(lat, lon, point.lat, point.lon)
            if nearest_distance is None or distance < nearest_distance:
                nearest = point
                nearest_distance = distance

        if nearest is None or nearest_distance is None:
            return None

        walking_distance = estimate_walking_distance_meters(
            nearest_distance,
            self.walking_detour_factor,
        )
        walking_minutes = estimate_walking_minutes(
            walking_distance,
            self.walking_speed_m_per_min,
        )
        return NearestPOIResult(
            poi=nearest,
            distance_meters=nearest_distance,
            walking_distance_meters_estimate=walking_distance,
            walking_minutes_estimate=walking_minutes,
        )
