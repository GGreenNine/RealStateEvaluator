import argparse
import json
import logging
import sys
from pathlib import Path

from scraper.config import ScraperConfig
from scraper.pipeline import OikotieScraper
from scraper.storage import save_json, save_run_listing_files
from scraper.utils import parse_bool, utcnow_iso


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Oikotie apartment listings into JSON."
    )
    parser.add_argument("--start-url", required=True, help="Listing URL to start from.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=30,
        help="Maximum number of listing pages to scan.",
    )
    parser.add_argument(
        "--all-pages",
        action="store_true",
        help="Scan all pages until the end of pagination or until pages become empty.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between HTTP requests in seconds.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--output",
        default="data/listings_latest.json",
        help="Path to the latest snapshot JSON file.",
    )
    parser.add_argument(
        "--state-file",
        default="data/state.json",
        help="Path to scraper state JSON file.",
    )
    parser.add_argument(
        "--history-dir",
        default="data/runs",
        help="Directory where per-run snapshots are stored.",
    )
    parser.add_argument(
        "--browser-fallback",
        action="store_true",
        help="Use Playwright as a fallback when requests HTML is insufficient.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose logging.",
    )
    parser.add_argument(
        "--save-debug-html",
        action="store_true",
        help="Save fetched HTML pages for debugging when parsing fails.",
    )
    parser.add_argument(
        "--stop-on-error",
        type=parse_bool,
        default=False,
        help="Stop immediately when a single listing or page fails.",
    )
    return parser


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.debug)

    config = ScraperConfig(
        start_url=args.start_url,
        max_pages=args.max_pages,
        all_pages=args.all_pages,
        delay=args.delay,
        timeout=args.timeout,
        output_path=Path(args.output),
        state_file=Path(args.state_file),
        history_dir=Path(args.history_dir),
        browser_fallback=args.browser_fallback,
        debug=args.debug,
        stop_on_error=args.stop_on_error,
        save_debug_html=args.save_debug_html,
    )

    scraper = OikotieScraper(config=config)
    run_started_at = utcnow_iso()

    try:
        payload = scraper.run()
    except KeyboardInterrupt:
        logging.warning("Interrupted by user. Saving partial results without updating state.")
        partial_payload = scraper.build_partial_payload(run_started_at=run_started_at)
        if partial_payload["records"]:
            save_json(config.output_path, partial_payload)
            run_dir = save_run_listing_files(config.history_dir, partial_payload)
            logging.warning("Partial snapshot saved to %s and %s", config.output_path, run_dir)
        return 130
    except Exception:
        logging.exception("Scraper failed.")
        return 1
    finally:
        scraper.close()

    save_json(config.output_path, payload)
    run_dir = save_run_listing_files(config.history_dir, payload)

    logging.info(
        "Run completed. Saved %s records to %s and %s",
        len(payload["records"]),
        config.output_path,
        run_dir,
    )

    json.dump(
        {
            "output": str(config.output_path),
            "history": str(run_dir),
            "records": len(payload["records"]),
            "errors": len(payload.get("errors", [])),
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
