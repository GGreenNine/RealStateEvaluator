from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ...utils import normalize_coordinate
from ..models import POICategory, PointOfInterest
from .base import BasePOIProvider

LOGGER = logging.getLogger(__name__)

DEFAULT_DIGITRANSIT_GRAPHQL_URL = "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1"
STATIONS_QUERY = """
query StationsForPoiCategories {
  stations {
    gtfsId
    name
    lat
    lon
    stops {
      gtfsId
      vehicleMode
      lat
      lon
    }
  }
}
""".strip()
STOPS_QUERY = """
query StopsForPoiCategories {
  stops {
    gtfsId
    name
    lat
    lon
    vehicleMode
    code
    parentStation {
      gtfsId
      name
      lat
      lon
    }
  }
}
""".strip()


@dataclass(slots=True)
class DigitransitProviderConfig:
    endpoint_url: str = field(
        default_factory=lambda: os.getenv(
            "DIGITRANSIT_GRAPHQL_URL",
            DEFAULT_DIGITRANSIT_GRAPHQL_URL,
        )
    )
    subscription_key: str | None = field(
        default_factory=lambda: os.getenv("DIGITRANSIT_SUBSCRIPTION_KEY")
    )
    timeout: float = 20.0
    retry_total: int = 3
    retry_backoff_factor: float = 1.0
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    headers: dict[str, str] = field(
        default_factory=lambda: {
            "User-Agent": "OikotieScraper/1.0 DigitransitPOIProvider",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )


class DigitransitPOIProvider(BasePOIProvider):
    source_name = "digitransit_hsl"

    def __init__(self, config: DigitransitProviderConfig) -> None:
        self.config = config
        self.session = requests.Session()
        retry = Retry(
            total=config.retry_total,
            backoff_factor=config.retry_backoff_factor,
            status_forcelist=list(config.retry_statuses),
            allowed_methods=["POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(config.headers)
        if config.subscription_key:
            self.session.headers.update(
                {
                    "digitransit-subscription-key": config.subscription_key,
                    "Ocp-Apim-Subscription-Key": config.subscription_key,
                }
            )

    def close(self) -> None:
        self.session.close()

    def fetch(self, category: POICategory) -> list[PointOfInterest]:
        if category is POICategory.METRO_STATION:
            return self.fetch_metro_stations()
        if category is POICategory.TRAM_STOP:
            return self.fetch_tram_stops()
        if category is POICategory.RAIL_STATION:
            return self.fetch_rail_stations()
        raise NotImplementedError(
            f"Digitransit provider does not yet support {category.value}"
        )

    def fetch_metro_stations(self) -> list[PointOfInterest]:
        stations = self._fetch_stations()
        return self._normalize_station_category(
            stations=stations,
            category=POICategory.METRO_STATION,
            required_mode="SUBWAY",
        )

    def fetch_tram_stops(self) -> list[PointOfInterest]:
        stops = self._fetch_stops()
        return self._normalize_tram_stops(stops)

    def fetch_rail_stations(self) -> list[PointOfInterest]:
        stations = self._fetch_stations()
        return self._normalize_station_category(
            stations=stations,
            category=POICategory.RAIL_STATION,
            required_mode="RAIL",
        )

    def _fetch_stations(self) -> list[dict[str, Any]]:
        payload = self._post_graphql(STATIONS_QUERY)
        stations = payload.get("data", {}).get("stations", [])
        if not isinstance(stations, list):
            raise RuntimeError("Unexpected Digitransit response: stations is not a list")
        return stations

    def _fetch_stops(self) -> list[dict[str, Any]]:
        payload = self._post_graphql(STOPS_QUERY)
        stops = payload.get("data", {}).get("stops", [])
        if not isinstance(stops, list):
            raise RuntimeError("Unexpected Digitransit response: stops is not a list")
        return stops

    def _post_graphql(self, query: str) -> dict[str, Any]:
        response = self.session.post(
            self.config.endpoint_url,
            json={"query": query},
            timeout=self.config.timeout,
        )
        if response.status_code in {401, 403} and not self.config.subscription_key:
            raise RuntimeError(
                "Digitransit request was rejected. Set DIGITRANSIT_SUBSCRIPTION_KEY "
                "if your Digitransit subscription requires it."
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Digitransit GraphQL request failed with HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Digitransit response was not valid JSON") from exc
        errors = payload.get("errors")
        if errors:
            raise RuntimeError(f"Digitransit GraphQL returned errors: {errors}")
        return payload

    def _normalize_station_category(
        self,
        stations: list[dict[str, Any]],
        category: POICategory,
        required_mode: str,
    ) -> list[PointOfInterest]:
        normalized: list[PointOfInterest] = []
        seen_ids: set[str] = set()

        for station in stations:
            if not isinstance(station, dict):
                continue

            raw_stops = station.get("stops") or []
            stop_modes = sorted(
                {
                    str(stop.get("vehicleMode"))
                    for stop in raw_stops
                    if isinstance(stop, dict) and stop.get("vehicleMode")
                }
            )
            if required_mode not in stop_modes:
                continue

            station_id = station.get("gtfsId")
            if not station_id:
                continue
            station_id = str(station_id)
            if station_id in seen_ids:
                continue

            lat = normalize_coordinate(station.get("lat"))
            lon = normalize_coordinate(station.get("lon"))
            if lat is None or lon is None:
                lat, lon = self._fallback_stop_coordinates(raw_stops)
            if lat is None or lon is None:
                LOGGER.warning("Skipping metro station without coordinates: %s", station_id)
                continue

            stop_ids = [
                str(stop.get("gtfsId"))
                for stop in raw_stops
                if isinstance(stop, dict) and stop.get("gtfsId")
            ]

            normalized.append(
                PointOfInterest(
                    id=station_id,
                    name=str(station.get("name") or station_id),
                    lat=lat,
                    lon=lon,
                    category=category.value,
                    source=self.source_name,
                    raw_modes=stop_modes,
                    stop_ids=stop_ids,
                    metadata={
                        "normalization_level": "station",
                        "stop_count": len(stop_ids),
                    },
                )
            )
            seen_ids.add(station_id)

        normalized.sort(key=lambda item: item.name.casefold())
        return normalized

    def _normalize_tram_stops(
        self,
        stops: list[dict[str, Any]],
    ) -> list[PointOfInterest]:
        normalized: list[PointOfInterest] = []
        seen_ids: set[str] = set()

        for stop in stops:
            if not isinstance(stop, dict):
                continue
            vehicle_mode = str(stop.get("vehicleMode") or "").upper()
            if vehicle_mode != "TRAM":
                continue

            stop_id = stop.get("gtfsId")
            if not stop_id:
                continue
            stop_id = str(stop_id)
            if stop_id in seen_ids:
                continue

            lat = normalize_coordinate(stop.get("lat"))
            lon = normalize_coordinate(stop.get("lon"))
            if lat is None or lon is None:
                continue

            parent_station = stop.get("parentStation")
            metadata: dict[str, Any] = {
                "normalization_level": "stop",
                "code": stop.get("code"),
            }
            if isinstance(parent_station, dict) and parent_station.get("gtfsId"):
                metadata["parent_station_id"] = str(parent_station.get("gtfsId"))
                metadata["parent_station_name"] = str(
                    parent_station.get("name") or parent_station.get("gtfsId")
                )

            normalized.append(
                PointOfInterest(
                    id=stop_id,
                    name=str(stop.get("name") or stop_id),
                    lat=lat,
                    lon=lon,
                    category=POICategory.TRAM_STOP.value,
                    source=self.source_name,
                    raw_modes=["TRAM"],
                    stop_ids=[stop_id],
                    metadata=metadata,
                )
            )
            seen_ids.add(stop_id)

        normalized.sort(key=lambda item: item.name.casefold())
        return normalized

    def _fallback_stop_coordinates(
        self,
        stops: list[dict[str, Any]],
    ) -> tuple[float | None, float | None]:
        for stop in stops:
            if not isinstance(stop, dict):
                continue
            lat = normalize_coordinate(stop.get("lat"))
            lon = normalize_coordinate(stop.get("lon"))
            if lat is not None and lon is not None:
                return lat, lon
        return None, None
