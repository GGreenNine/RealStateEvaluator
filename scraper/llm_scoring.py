from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel

from .analysis_config import ApartmentAnalysisConfig
from .analysis_models import DerivedAnalysisFields, LLMScoreResult


LOGGER = logging.getLogger(__name__)


class LLMScoringError(RuntimeError):
    pass


class LLMDerivedAssumptions(BaseModel):
    estimated_commute_minutes_to_helsinki_center: float | None
    repair_risk_level: str


class LLMScorePayload(BaseModel):
    listing_id: str | None
    renovations_score: float
    commute_score: float
    llm_total_score: float
    confidence: float
    recommendation: str
    summary: str
    reasoning_notes: list[str]
    derived_assumptions: LLMDerivedAssumptions


def _validate_score(name: str, value: Any, max_points: float) -> float:
    if not isinstance(value, (int, float)):
        raise LLMScoringError(f"{name} must be numeric")
    normalized = round(float(value), 2)
    if normalized < 0 or normalized > max_points:
        raise LLMScoringError(f"{name} must be between 0 and {max_points}")
    return normalized


def _validate_payload(payload: Mapping[str, Any], config: ApartmentAnalysisConfig) -> LLMScoreResult:
    renovations_score = _validate_score(
        "renovations_score",
        payload.get("renovations_score"),
        config.llm_scoring.renovations.max_points,
    )
    commute_score = _validate_score(
        "commute_score",
        payload.get("commute_score"),
        config.llm_scoring.commute.max_points,
    )

    llm_total_score = round(
        renovations_score + commute_score,
        2,
    )
    returned_total = payload.get("llm_total_score")
    if not isinstance(returned_total, (int, float)):
        raise LLMScoringError("llm_total_score must be numeric")
    if round(float(returned_total), 2) != llm_total_score:
        raise LLMScoringError("llm_total_score does not match criterion sum")

    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)):
        raise LLMScoringError("confidence must be numeric")
    confidence_value = round(float(confidence), 4)
    if confidence_value < 0 or confidence_value > 1:
        raise LLMScoringError("confidence must be between 0 and 1")

    recommendation = payload.get("recommendation")
    if recommendation not in {"reject", "review", "shortlist"}:
        raise LLMScoringError("recommendation must be reject, review, or shortlist")

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise LLMScoringError("summary must be a non-empty string")

    reasoning_notes = payload.get("reasoning_notes")
    if not isinstance(reasoning_notes, list) or not all(
        isinstance(note, str) and note.strip() for note in reasoning_notes
    ):
        raise LLMScoringError("reasoning_notes must be a list of non-empty strings")

    derived_assumptions = payload.get("derived_assumptions")
    if not isinstance(derived_assumptions, dict):
        raise LLMScoringError("derived_assumptions must be an object")

    return LLMScoreResult(
        listing_id=payload.get("listing_id"),
        renovations_score=renovations_score,
        commute_score=commute_score,
        llm_total_score=llm_total_score,
        confidence=confidence_value,
        recommendation=recommendation,
        summary=summary.strip(),
        reasoning_notes=[note.strip() for note in reasoning_notes],
        derived_assumptions=dict(derived_assumptions),
    )


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


class OpenAILLMScorer:
    def __init__(self, config: ApartmentAnalysisConfig) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMScoringError(
                "openai package is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        self.config = config
        self.prompt_text = _load_prompt(config.openai.prompt_path)
        self.client = OpenAI(timeout=config.openai.timeout_seconds)

    def _call_model(self, listing: Mapping[str, Any], derived: DerivedAnalysisFields) -> dict[str, Any]:
        user_payload = {
            "listing": dict(listing),
            "derived_fields": derived.to_dict(),
        }
        request_payload = {
            "model": self.config.openai.model,
            "max_output_tokens": self.config.openai.max_output_tokens,
            "instructions": self.prompt_text,
            "input": json.dumps(user_payload, ensure_ascii=False, indent=2),
            "reasoning": {"effort": "minimal"},
            "text": {"verbosity": "low"},
        }
        # GPT-5 models currently reject temperature on the Responses API.
        if not self.config.openai.model.lower().startswith("gpt-5"):
            request_payload["temperature"] = self.config.openai.temperature

        response = self.client.responses.parse(
            text_format=LLMScorePayload,
            **request_payload,
        )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            output_types = [getattr(item, "type", None) for item in getattr(response, "output", []) or []]
            status = getattr(response, "status", None)
            incomplete_details = getattr(response, "incomplete_details", None)
            usage = getattr(response, "usage", None)
            raise LLMScoringError(
                "Model returned no parsed structured output. "
                f"status={status}, output_item_types={output_types}, "
                f"incomplete_details={incomplete_details}, usage={usage}"
            )
        return parsed.model_dump()

    def score_listing(
        self,
        listing: Mapping[str, Any],
        derived: DerivedAnalysisFields,
    ) -> LLMScoreResult:
        last_error: Exception | None = None
        for attempt in range(1, self.config.openai.retries + 1):
            try:
                payload = self._call_model(listing, derived)
                return _validate_payload(payload, self.config)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                LOGGER.warning(
                    "LLM scoring attempt %s/%s failed for listing %s: %s",
                    attempt,
                    self.config.openai.retries,
                    listing.get("listing_id") or listing.get("url"),
                    exc,
                )
        raise LLMScoringError(str(last_error)) from last_error
