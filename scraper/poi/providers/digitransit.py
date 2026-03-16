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
METRO_STATIONS_QUERY = """
query MetroStations {
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
        if category is not POICategory.METRO_STATION:
            raise NotImplementedError(
                f"Digitransit metro provider does not yet support {category.value}"
            )
        payload = self._post_graphql(METRO_STATIONS_QUERY)
        stations = payload.get("data", {}).get("stations", [])
        if not isinstance(stations, list):
            raise RuntimeError("Unexpected Digitransit response: stations is not a list")
        return self._normalize_metro_stations(stations)

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

    def _normalize_metro_stations(
        self,
        stations: list[dict[str, Any]],
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
            if "SUBWAY" not in stop_modes:
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
                    category=POICategory.METRO_STATION.value,
                    source=self.source_name,
                    raw_modes=stop_modes,
                    stop_ids=stop_ids,
                    metadata={
                        "stop_count": len(stop_ids),
                    },
                )
            )
            seen_ids.add(station_id)

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
