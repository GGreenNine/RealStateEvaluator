from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class DerivedAnalysisFields:
    normalized_rooms: int | None
    calculated_price_per_m2: float | None
    maintenance_fee_per_m2: float | None
    input_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HardScoreResult:
    room_gate_status: str
    room_gate_passed: bool
    building_age_score: float
    plot_ownership_score: float
    price_per_m2_score: float
    size_score: float
    maintenance_fee_per_m2: float | None
    maintenance_fee_score: float
    metro_score: float
    tram_score: float
    rail_score: float
    transit_score: float
    multimodal_bonus: float
    floor_score: float
    value_score: float
    technical_risk_score: float
    hard_total_score: float
    disqualified: bool
    disqualification_reason: str | None = None
    review_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LLMScoreResult:
    listing_id: str | None
    renovations_score: float
    llm_total_score: float
    confidence: float
    recommendation: str
    summary: str
    reasoning_notes: list[str] = field(default_factory=list)
    derived_assumptions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ApartmentScoreRecord:
    listing_id: str | None
    input_file: str
    input_hash: str | None
    prompt_version: str | None
    model: str | None
    llm_input_file: str | None
    listing: dict[str, Any]
    llm_input_payload: dict[str, Any] | None
    derived_fields: dict[str, Any]
    hard_scores: dict[str, Any]
    category_scores: dict[str, float]
    llm_scores: dict[str, Any] | None
    hard_total_score: float
    llm_total_score: float
    final_total_score: float
    disqualified: bool
    disqualification_reason: str | None
    llm_skipped_reason: str | None
    llm_error: str | None
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
