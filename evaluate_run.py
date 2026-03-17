import argparse
import json
import logging
from pathlib import Path

from scraper.analysis_config import load_apartment_analysis_config
from scraper.analysis_models import ApartmentScoreRecord
from scraper.hard_scoring import compute_hard_scores
from scraper.llm_payload import build_llm_input_payload
from scraper.leaderboard import scored_output_path
from scraper.llm_scoring import LLMScoreResult, OpenAILLMScorer
from scraper.storage import save_json
from scraper.utils import ensure_dir, utcnow_iso


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate one scraped run directory with hard and LLM scoring.",
    )
    parser.add_argument("--run-dir", required=True, help="Path to one data/runs/<timestamp> directory.")
    parser.add_argument(
        "--config",
        default="config/apartment_analysis.yaml",
        help="Path to apartment analysis YAML config.",
    )
    parser.add_argument(
        "--build-leaderboard",
        action="store_true",
        help="Run leaderboard build after scoring finishes.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging.")
    return parser


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _load_listing(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _looks_like_listing(payload: dict) -> bool:
    return isinstance(payload, dict) and any(
        key in payload for key in ("listing_id", "url", "price_total_value", "address")
    )


def _zero_llm_score(listing_id: str | None, summary: str) -> LLMScoreResult:
    return LLMScoreResult(
        listing_id=listing_id,
        renovations_score=0.0,
        llm_total_score=0.0,
        confidence=1.0,
        recommendation="reject",
        summary=summary,
        reasoning_notes=[summary],
        derived_assumptions={
            "repair_risk_level": "unknown",
        },
    )


def _existing_score_matches(score_path: Path, input_hash: str, prompt_version: str) -> bool:
    if not score_path.exists():
        return False
    try:
        payload = json.loads(score_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        payload.get("input_hash") == input_hash
        and payload.get("prompt_version") == prompt_version
        and not payload.get("llm_error")
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.debug)

    config = load_apartment_analysis_config(Path(args.config))
    run_dir = Path(args.run_dir).resolve()
    scored_dir = run_dir / config.paths.scored_dir_name
    llm_payload_dir = run_dir / config.paths.llm_payload_dir_name
    ensure_dir(scored_dir)
    ensure_dir(llm_payload_dir)

    listing_files = sorted(
        path
        for path in run_dir.glob("*.json")
        if path.is_file() and path.name != "_run.json" and not path.name.endswith(".score.json")
    )

    if not listing_files:
        logging.error("No apartment JSON files found in %s", run_dir)
        return 1

    scorer: OpenAILLMScorer | None = None
    processed = 0
    skipped = 0

    for listing_path in listing_files:
        listing = _load_listing(listing_path)
        if listing_path.name == config.paths.leaderboard_json_name or not _looks_like_listing(listing):
            logging.debug("Skipping non-listing JSON file %s", listing_path.name)
            skipped += 1
            continue

        if config.filters.reject_parse_error and listing.get("parse_error"):
            logging.warning("Skipping %s due to parse_error", listing_path.name)
            skipped += 1
            continue

        derived, hard_scores = compute_hard_scores(listing, config)
        llm_input_payload, llm_input_debug = build_llm_input_payload(listing, config)
        score_path = scored_output_path(scored_dir, listing_path)
        llm_payload_path = llm_payload_dir / f"{listing_path.stem}.llm-input.json"
        save_json(llm_payload_path, llm_input_debug)
        logging.debug("Saved reduced LLM payload to %s", llm_payload_path)

        if (
            config.filters.skip_if_already_scored
            and _existing_score_matches(score_path, derived.input_hash, config.prompt_version)
        ):
            logging.info("Skipping unchanged scored listing %s", listing_path.name)
            skipped += 1
            continue

        llm_error: str | None = None
        llm_skipped_reason: str | None = None
        if hard_scores.disqualified:
            llm_skipped_reason = (
                f"hard_disqualified:{hard_scores.disqualification_reason or 'disqualified'}"
            )
            llm_scores = _zero_llm_score(
                listing.get("listing_id"),
                f"Rejected by hard gate: {hard_scores.disqualification_reason or 'disqualified'}",
            )
        elif hard_scores.hard_total_score < config.filters.min_hard_score_for_llm:
            llm_skipped_reason = (
                f"hard_total_score_below_threshold:{hard_scores.hard_total_score}"
            )
            llm_scores = _zero_llm_score(
                listing.get("listing_id"),
                (
                    "LLM skipped because hard_total_score is below "
                    f"{config.filters.min_hard_score_for_llm}."
                ),
            )
        else:
            try:
                if scorer is None:
                    scorer = OpenAILLMScorer(config)
                llm_scores = scorer.score_listing(llm_input_payload, derived)
            except Exception as exc:  # noqa: BLE001
                llm_error = str(exc)
                logging.error("LLM scoring failed for %s: %s", listing_path.name, exc)
                llm_scores = _zero_llm_score(
                    listing.get("listing_id"),
                    "LLM scoring failed; scores set to zero for this run.",
                )

        category_scores = {
            "value_score": hard_scores.value_score,
            "technical_risk_score": round(
                hard_scores.technical_risk_score + llm_scores.renovations_score,
                2,
            ),
            "transit_score": hard_scores.transit_score,
        }
        final_total_score = (
            0.0
            if hard_scores.disqualified
            else round(
                category_scores["value_score"]
                + category_scores["technical_risk_score"]
                + category_scores["transit_score"]
                + hard_scores.plot_ownership_score
                + hard_scores.maintenance_fee_score
                + hard_scores.floor_score,
                2,
            )
        )

        scored_record = ApartmentScoreRecord(
            listing_id=listing.get("listing_id"),
            input_file=listing_path.name,
            input_hash=derived.input_hash if config.metadata.save_input_hash else None,
            prompt_version=config.prompt_version if config.metadata.save_prompt_version else None,
            model=config.openai.model if config.metadata.save_model_name else None,
            llm_input_file=str(llm_payload_path.relative_to(run_dir)),
            listing=listing,
            llm_input_payload=llm_input_payload,
            derived_fields=derived.to_dict(),
            hard_scores=hard_scores.to_dict(),
            category_scores=category_scores,
            llm_scores=llm_scores.to_dict(),
            hard_total_score=hard_scores.hard_total_score,
            llm_total_score=llm_scores.llm_total_score,
            final_total_score=final_total_score,
            disqualified=hard_scores.disqualified,
            disqualification_reason=hard_scores.disqualification_reason,
            llm_skipped_reason=llm_skipped_reason,
            llm_error=llm_error,
            evaluated_at=utcnow_iso(),
        )
        save_json(score_path, scored_record.to_dict())
        logging.info("Saved scored listing to %s", score_path)
        processed += 1

    if args.build_leaderboard:
        from build_leaderboard import build_for_run_dir

        build_for_run_dir(run_dir=run_dir, config_path=Path(args.config))

    logging.info(
        "Run evaluation completed for %s. Processed=%s, skipped=%s",
        run_dir,
        processed,
        skipped,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
