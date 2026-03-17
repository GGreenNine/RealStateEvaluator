from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .analysis_config import ApartmentAnalysisConfig, ScoreAnchorConfig
from .analysis_models import DerivedAnalysisFields, HardScoreResult
from .utils import normalize_land_ownership, normalize_text


ROOM_RE = re.compile(r"(?<!\d)(\d+)(?:\s*h|\s*huon|$)", re.IGNORECASE)
ANY_NUMBER_RE = re.compile(r"(?<!\d)(\d+)(?!\d)")


def _round_score(value: float) -> float:
    return round(value, 2)


def _interpolate_score(
    value: float | int | None,
    anchors: tuple[ScoreAnchorConfig, ...],
    below_first_points: float | None = None,
) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    if not anchors:
        return 0.0

    numeric = float(value)
    first = anchors[0]
    last = anchors[-1]

    if numeric < first.value:
        return float(below_first_points if below_first_points is not None else first.points)
    if numeric == first.value:
        return float(first.points)
    if numeric >= last.value:
        return float(last.points)

    for left, right in zip(anchors, anchors[1:]):
        if numeric == right.value:
            return float(right.points)
        if left.value <= numeric <= right.value:
            if right.value == left.value:
                return float(right.points)
            ratio = (numeric - left.value) / (right.value - left.value)
            return float(left.points + ratio * (right.points - left.points))
    return float(last.points)


def _score_maintenance_fee_per_m2(
    value: float | int | None,
    best_fee_per_m2: float,
    worst_fee_per_m2: float,
    max_points: float,
    min_points: float,
) -> float:
    if not isinstance(value, (int, float)):
        return min_points
    numeric = float(value)
    if numeric <= best_fee_per_m2:
        return max_points
    if numeric >= worst_fee_per_m2:
        return min_points
    if worst_fee_per_m2 <= best_fee_per_m2:
        return min_points
    ratio = (numeric - best_fee_per_m2) / (worst_fee_per_m2 - best_fee_per_m2)
    return float(max_points - ratio * (max_points - min_points))


def _extract_room_count_from_text(value: str | None) -> int | None:
    text = normalize_text(value)
    if not text:
        return None

    match = ROOM_RE.search(text)
    if match:
        return int(match.group(1))

    match = ANY_NUMBER_RE.search(text)
    if match:
        return int(match.group(1))
    return None


def normalize_room_count(record: Mapping[str, Any]) -> int | None:
    card = record.get("card") if isinstance(record.get("card"), dict) else {}
    candidates = [
        record.get("rooms"),
        record.get("title"),
        record.get("description"),
        card.get("rooms"),
        card.get("meta_raw"),
    ]
    for candidate in candidates:
        value = _extract_room_count_from_text(candidate)
        if value is not None:
            return value
    return None


def calculate_price_per_m2(record: Mapping[str, Any]) -> float | None:
    existing = record.get("price_per_m2_value")
    if isinstance(existing, (int, float)) and existing > 0:
        return round(float(existing), 2)

    price_total = record.get("price_total_value")
    area = record.get("area_m2_value")
    if not isinstance(price_total, (int, float)) or not isinstance(area, (int, float)):
        return None
    if area <= 0:
        return None
    return round(float(price_total) / float(area), 2)


def calculate_maintenance_fee_per_m2(record: Mapping[str, Any]) -> float | None:
    maintenance_fee = record.get("maintenance_fee_value")
    area = record.get("area_m2_value")
    if not isinstance(maintenance_fee, (int, float)) or not isinstance(area, (int, float)):
        return None
    if area <= 0:
        return None
    return round(float(maintenance_fee) / float(area), 3)


def _normalized_transit_mode_score(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def build_input_hash(record: Mapping[str, Any], normalized_rooms: int | None) -> str:
    payload = {
        "listing_id": record.get("listing_id"),
        "url": record.get("url"),
        "price_total_value": record.get("price_total_value"),
        "price_per_m2_value": record.get("price_per_m2_value"),
        "area_m2_value": record.get("area_m2_value"),
        "maintenance_fee_value": record.get("maintenance_fee_value"),
        "building_year": record.get("building_year"),
        "floor_current": record.get("floor_current"),
        "floor_total": record.get("floor_total"),
        "planned_repairs": record.get("planned_repairs"),
        "completed_repairs": record.get("completed_repairs"),
        "land_ownership_normalized": record.get("land_ownership_normalized"),
        "land_ownership": record.get("land_ownership"),
        "rooms": record.get("rooms"),
        "normalized_rooms": normalized_rooms,
        "address": record.get("address"),
        "district": record.get("district"),
        "city": record.get("city"),
        "description": record.get("description"),
        "title": record.get("title"),
        "metro_score": record.get("metro_score"),
        "tram_score": record.get("tram_score"),
        "rail_score": record.get("rail_score"),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_hard_scores(
    record: Mapping[str, Any],
    config: ApartmentAnalysisConfig,
) -> tuple[DerivedAnalysisFields, HardScoreResult]:
    normalized_rooms = normalize_room_count(record)
    calculated_price_per_m2 = calculate_price_per_m2(record)
    maintenance_fee_per_m2 = calculate_maintenance_fee_per_m2(record)
    input_hash = build_input_hash(record, normalized_rooms)

    derived = DerivedAnalysisFields(
        normalized_rooms=normalized_rooms,
        calculated_price_per_m2=calculated_price_per_m2,
        maintenance_fee_per_m2=maintenance_fee_per_m2,
        input_hash=input_hash,
    )

    room_gate_cfg = config.hard_scoring.room_gate
    room_gate_passed = True
    room_gate_status = "pass"
    disqualified = False
    disqualification_reason: str | None = None
    review_reason: str | None = None

    if room_gate_cfg.enabled:
        if normalized_rooms is None:
            room_gate_passed = False
            if room_gate_cfg.unknown_rooms_action == "review":
                room_gate_status = "review"
                review_reason = "room_count_unknown"
            elif room_gate_cfg.disqualify_below_min_rooms:
                room_gate_status = "reject"
                disqualified = True
                disqualification_reason = "room_count_unknown"
        elif normalized_rooms < room_gate_cfg.min_rooms:
            room_gate_passed = False
            room_gate_status = "reject"
            if room_gate_cfg.disqualify_below_min_rooms:
                disqualified = True
                disqualification_reason = "room_count_below_minimum"

    building_age_score = _interpolate_score(
        record.get("building_year"),
        config.hard_scoring.building_age.anchors,
    )

    land_ownership = record.get("land_ownership_normalized")
    if not land_ownership:
        land_ownership = normalize_land_ownership(record.get("land_ownership"))
    if land_ownership == "owned":
        plot_ownership_score = config.hard_scoring.plot_ownership.owned_points
    elif land_ownership == "leased":
        plot_ownership_score = config.hard_scoring.plot_ownership.leased_points
    else:
        plot_ownership_score = config.hard_scoring.plot_ownership.unknown_points

    price_per_m2_score = _interpolate_score(
        calculated_price_per_m2,
        config.hard_scoring.price_per_m2.anchors,
    )

    size_score = _interpolate_score(
        record.get("area_m2_value"),
        config.hard_scoring.size.anchors,
        below_first_points=config.hard_scoring.size.below_min_points,
    )

    maintenance_fee_score = _score_maintenance_fee_per_m2(
        maintenance_fee_per_m2,
        config.hard_scoring.maintenance_fee.best_fee_per_m2,
        config.hard_scoring.maintenance_fee.worst_fee_per_m2,
        config.hard_scoring.maintenance_fee.max_points,
        config.hard_scoring.maintenance_fee.min_points,
    )

    metro_score = _normalized_transit_mode_score(record.get("metro_score"))
    tram_score = _normalized_transit_mode_score(record.get("tram_score"))
    rail_score = _normalized_transit_mode_score(record.get("rail_score"))
    transit_base = max(metro_score, tram_score, rail_score)
    strong_modes = sum(
        1
        for score in (metro_score, tram_score, rail_score)
        if score >= config.hard_scoring.transit.strong_score_threshold
    )
    multimodal_bonus = (
        config.hard_scoring.transit.multimodal_bonus
        if strong_modes >= 2
        else 0.0
    )
    transit_score = transit_base + multimodal_bonus

    floor_current = record.get("floor_current")
    if isinstance(floor_current, int):
        if floor_current == 1:
            floor_score = config.hard_scoring.floor.first_floor_points
        else:
            floor_score = config.hard_scoring.floor.other_floors_points
    else:
        floor_score = config.hard_scoring.floor.unknown_floor_points

    value_score = price_per_m2_score + size_score
    technical_risk_score = building_age_score

    if disqualified:
        hard_total_score = room_gate_cfg.fail_score
    else:
        hard_total_score = (
            value_score
            + plot_ownership_score
            + maintenance_fee_score
            + technical_risk_score
            + transit_score
            + floor_score
        )

    result = HardScoreResult(
        room_gate_status=room_gate_status,
        room_gate_passed=room_gate_passed,
        building_age_score=_round_score(building_age_score),
        plot_ownership_score=_round_score(plot_ownership_score),
        price_per_m2_score=_round_score(price_per_m2_score),
        size_score=_round_score(size_score),
        maintenance_fee_per_m2=maintenance_fee_per_m2,
        maintenance_fee_score=_round_score(maintenance_fee_score),
        metro_score=_round_score(metro_score),
        tram_score=_round_score(tram_score),
        rail_score=_round_score(rail_score),
        transit_score=_round_score(transit_score),
        multimodal_bonus=_round_score(multimodal_bonus),
        floor_score=_round_score(floor_score),
        value_score=_round_score(value_score),
        technical_risk_score=_round_score(technical_risk_score),
        hard_total_score=_round_score(hard_total_score),
        disqualified=disqualified,
        disqualification_reason=disqualification_reason,
        review_reason=review_reason,
    )
    return derived, result
