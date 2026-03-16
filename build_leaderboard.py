import argparse
import logging
from pathlib import Path

from scraper.analysis_config import load_apartment_analysis_config
from scraper.leaderboard import (
    build_leaderboard_rows,
    load_scored_records,
    write_leaderboard_outputs,
)


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def build_for_run_dir(run_dir: Path, config_path: Path) -> tuple[Path, Path | None]:
    config = load_apartment_analysis_config(config_path)
    scored_dir = run_dir / config.paths.scored_dir_name
    scored_records = load_scored_records(scored_dir)
    if not scored_records:
        raise SystemExit(f"No scored JSON files found in {scored_dir}")

    rows = build_leaderboard_rows(scored_records, config)
    csv_path, json_path = write_leaderboard_outputs(run_dir, rows, config)
    logging.info("Leaderboard written to %s", csv_path)
    if json_path:
        logging.info("Leaderboard JSON written to %s", json_path)
    return csv_path, json_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build leaderboard from scored listing JSON files.")
    parser.add_argument("--run-dir", required=True, help="Path to one data/runs/<timestamp> directory.")
    parser.add_argument(
        "--config",
        default="config/apartment_analysis.yaml",
        help="Path to apartment analysis YAML config.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.debug)
    build_for_run_dir(Path(args.run_dir).resolve(), Path(args.config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
