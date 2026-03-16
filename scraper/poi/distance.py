from __future__ import annotations

import math


EARTH_RADIUS_METERS = 6_371_000


def haversine_distance_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_METERS * c


def estimate_walking_distance_meters(
    distance_meters: float,
    walking_detour_factor: float,
) -> float:
    return distance_meters * walking_detour_factor


def estimate_walking_minutes(
    walking_distance_meters: float,
    walking_speed_m_per_min: float,
) -> float:
    if walking_speed_m_per_min <= 0:
        raise ValueError("walking_speed_m_per_min must be greater than zero")
    return walking_distance_meters / walking_speed_m_per_min
