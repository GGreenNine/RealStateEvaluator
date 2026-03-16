import argparse
import json
import logging
import sys
from pathlib import Path

from scraper.config import ScraperConfig
from scraper.pipeline import OikotieScraper
from scraper.poi.models import POICategory, POICollection
from scraper.poi.providers import DigitransitPOIProvider, DigitransitProviderConfig
from scraper.poi.repository import POIRepository
from scraper.storage import save_json, save_run_listing_files
from scraper.utils import parse_bool, utcnow_iso


LOGGER = logging.getLogger(__name__)
COMMAND_SCRAPE = "scrape"
COMMAND_FETCH_METRO = "fetch-metro-stations"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Oikotie apartment listings and manage local POI data."
    )
    subparsers = parser.add_subparsers(dest="command")

    build_scrape_parser(subparsers.add_parser(COMMAND_SCRAPE, help="Scrape Oikotie listings."))
    build_fetch_metro_parser(
        subparsers.add_parser(
            COMMAND_FETCH_METRO,
            help="Fetch metro stations from Digitransit and save them locally.",
        )
    )
    return parser


def build_scrape_parser(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument(
        "--enable-poi-enrichment",
        type=parse_bool,
        default=True,
        help="Enable nearest-POI enrichment from local data files.",
    )
    parser.add_argument(
        "--poi-data-dir",
        default="data/poi",
        help="Directory with local POI JSON files.",
    )
    parser.add_argument(
        "--metro-data-path",
        default="data/poi/metro_stations.json",
        help="Path to the local metro stations JSON file.",
    )
    parser.add_argument(
        "--walking-detour-factor",
        type=float,
        default=1.2,
        help="Multiplier used to estimate walking distance from straight-line distance.",
    )
    parser.add_argument(
        "--walking-speed-m-per-min",
        type=float,
        default=80.0,
        help="Estimated walking speed in meters per minute.",
    )


def build_fetch_metro_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        default=None,
        help="Where to save the local metro stations JSON file. Defaults to <poi-data-dir>/metro_stations.json.",
    )
    parser.add_argument(
        "--poi-data-dir",
        default="data/poi",
        help="Base directory for local POI JSON files.",
    )
    parser.add_argument(
        "--digitransit-endpoint",
        default=None,
        help="Override Digitransit GraphQL endpoint URL.",
    )
    parser.add_argument(
        "--subscription-key",
        default=None,
        help="Optional Digitransit subscription key. If omitted, DIGITRANSIT_SUBSCRIPTION_KEY is used.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--retry-total",
        type=int,
        default=3,
        help="Total number of retry attempts for temporary API errors.",
    )
    parser.add_argument(
        "--retry-backoff-factor",
        type=float,
        default=1.0,
        help="Retry backoff factor for temporary API errors.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose logging.",
    )


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    known_commands = {COMMAND_SCRAPE, COMMAND_FETCH_METRO, "-h", "--help"}
    if argv[0] not in known_commands:
        return [COMMAND_SCRAPE, *argv]
    return argv


def run_scrape(args: argparse.Namespace) -> int:
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
        enable_poi_enrichment=args.enable_poi_enrichment,
        poi_data_dir=Path(args.poi_data_dir),
        metro_data_path=Path(args.metro_data_path),
        walking_detour_factor=args.walking_detour_factor,
        walking_speed_m_per_min=args.walking_speed_m_per_min,
    )

    scraper = OikotieScraper(config=config)
    run_started_at = utcnow_iso()

    try:
        payload = scraper.run()
    except KeyboardInterrupt:
        LOGGER.warning("Interrupted by user. Saving partial results without updating state.")
        partial_payload = scraper.build_partial_payload(run_started_at=run_started_at)
        if partial_payload["records"]:
            save_json(config.output_path, partial_payload)
            run_dir = save_run_listing_files(config.history_dir, partial_payload)
            LOGGER.warning("Partial snapshot saved to %s and %s", config.output_path, run_dir)
        return 130
    except Exception:
        LOGGER.exception("Scraper failed.")
        return 1
    finally:
        scraper.close()

    save_json(config.output_path, payload)
    run_dir = save_run_listing_files(config.history_dir, payload)

    LOGGER.info(
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


def run_fetch_metro_stations(args: argparse.Namespace) -> int:
    repository = POIRepository(base_dir=Path(args.poi_data_dir))
    default_provider_config = DigitransitProviderConfig()
    provider_config = DigitransitProviderConfig(
        endpoint_url=args.digitransit_endpoint
        or default_provider_config.endpoint_url,
        subscription_key=args.subscription_key
        or default_provider_config.subscription_key,
        timeout=args.timeout,
        retry_total=args.retry_total,
        retry_backoff_factor=args.retry_backoff_factor,
    )
    provider = DigitransitPOIProvider(provider_config)

    try:
        items = provider.fetch(POICategory.METRO_STATION)
    except Exception:
        LOGGER.exception("Failed to fetch metro stations from Digitransit.")
        return 1
    finally:
        provider.close()

    collection = POICollection(
        source=provider.source_name,
        object_type=POICategory.METRO_STATION.value,
        fetched_at=utcnow_iso(),
        items=items,
    )
    output_path = repository.save_collection(
        collection,
        Path(args.output) if args.output else repository.path_for_category(POICategory.METRO_STATION),
    )

    LOGGER.info("Saved %s metro stations to %s", len(items), output_path)
    json.dump(
        {
            "source": provider.source_name,
            "object_type": POICategory.METRO_STATION.value,
            "count": len(items),
            "output": str(output_path),
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    normalized_argv = normalize_argv(list(argv) if argv is not None else sys.argv[1:])
    args = parser.parse_args(normalized_argv)
    configure_logging(getattr(args, "debug", False))

    if args.command == COMMAND_FETCH_METRO:
        return run_fetch_metro_stations(args)
    if args.command == COMMAND_SCRAPE:
        return run_scrape(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
