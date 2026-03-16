from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

from .client import HttpClient
from .config import ScraperConfig
from .models import ListingCard, ListingRecord
from .pagination import build_page_url, build_search_api_url
from .parsers import (
    listing_page_has_main_content,
    page_has_listing_cards,
    parse_listing_cards,
    parse_listing_cards_from_api,
    parse_listing_details,
    parse_total_pages,
)
from .poi import POICategory, POIRepository, POIService, score_metro_walking_minutes
from .state import apply_state, load_state, save_state
from .storage import save_text
from .utils import utcnow_iso

LOGGER = logging.getLogger(__name__)


class OikotieScraper:
    def __init__(self, config: ScraperConfig) -> None:
        self.config = config
        self.client = HttpClient(config)
        self.poi_service = POIService(
            repository=POIRepository(config.poi_data_dir),
            walking_detour_factor=config.walking_detour_factor,
            walking_speed_m_per_min=config.walking_speed_m_per_min,
        )
        self._records: list[ListingRecord] = []
        self._errors: list[dict[str, str]] = []
        self._pages_scanned = 0
        self._listing_urls_found = 0

    def build_partial_payload(self, run_started_at: str | None = None) -> dict:
        finished_at = utcnow_iso()
        return {
            "run": {
                "start_url": self.config.start_url,
                "started_at": run_started_at or finished_at,
                "finished_at": finished_at,
                "pages_scanned": self._pages_scanned,
                "listing_urls_found": self._listing_urls_found,
                "records_scraped": len(self._records),
                "browser_fallback": self.config.browser_fallback,
                "partial": True,
            },
            "records": [asdict(record) for record in self._records],
            "errors": list(self._errors),
        }

    def run(self) -> dict:
        run_started_at = utcnow_iso()
        previous_state = load_state(self.config.state_file)

        cards = self._collect_listing_cards()
        self._listing_urls_found = len(cards)
        self._records = self._collect_listing_details(cards)

        run_finished_at = utcnow_iso()
        updated_state = apply_state(self._records, previous_state, run_finished_at)
        save_state(self.config.state_file, updated_state)

        return {
            "run": {
                "start_url": self.config.start_url,
                "started_at": run_started_at,
                "finished_at": run_finished_at,
                "pages_scanned": self._pages_scanned,
                "listing_urls_found": self._listing_urls_found,
                "records_scraped": len(self._records),
                "browser_fallback": self.config.browser_fallback,
                "partial": False,
            },
            "records": [asdict(record) for record in self._records],
            "errors": list(self._errors),
        }

    def _collect_listing_cards(self) -> list[ListingCard]:
        api_cards = self._collect_listing_cards_via_api()
        if api_cards:
            return api_cards
        LOGGER.warning("Search API returned no cards, falling back to HTML listing parsing.")

        return self._collect_listing_cards_via_html()

    def _collect_listing_cards_via_api(self) -> list[ListingCard]:
        cards_by_url: dict[str, ListingCard] = {}
        page_number = 1
        known_total_pages: int | None = None
        bootstrap_headers: dict[str, str] | None = None

        while True:
            if not self.config.all_pages and page_number > self.config.max_pages:
                break
            if known_total_pages is not None and page_number > known_total_pages:
                break

            if bootstrap_headers is None:
                try:
                    bootstrap_headers = self.client.bootstrap_listing_api(self.config.start_url)
                    LOGGER.info("Bootstrapped listing API session from HTML page")
                except Exception as exc:
                    self._register_error(
                        self.config.start_url,
                        f"listing_api_bootstrap_failed: {exc}",
                    )
                    if self.config.stop_on_error:
                        raise
                    break

            api_url = build_search_api_url(
                self.config.start_url,
                page_number=page_number,
                page_size=self.config.page_size,
            )
            LOGGER.info("Fetching listing API page %s", api_url)

            try:
                payload = self.client.fetch_json(
                    api_url,
                    headers=bootstrap_headers,
                )
            except Exception as exc:
                self._register_error(api_url, f"listing_api_fetch_failed: {exc}")
                if self.config.stop_on_error:
                    raise
                break

            self._pages_scanned += 1

            found = payload.get("found")
            if isinstance(found, int) and found >= 0 and known_total_pages is None:
                known_total_pages = max(
                    1,
                    (found + self.config.page_size - 1) // self.config.page_size,
                )
                LOGGER.info("Detected %s listing pages from API", known_total_pages)

            cards = parse_listing_cards_from_api(payload)
            if not cards:
                LOGGER.warning("No listing cards returned by API on page %s", page_number)
                break

            for card in cards:
                cards_by_url.setdefault(card.url, card)

            if not self.config.all_pages and page_number >= self.config.max_pages:
                break
            page_number += 1

        return list(cards_by_url.values())

    def _collect_listing_cards_via_html(self) -> list[ListingCard]:
        cards_by_url: dict[str, ListingCard] = {}
        empty_pages_in_row = 0
        known_total_pages: int | None = None
        page_number = 1

        while True:
            if not self.config.all_pages and page_number > self.config.max_pages:
                break
            if known_total_pages is not None and page_number > known_total_pages:
                break

            page_url = build_page_url(self.config.start_url, page_number)
            LOGGER.info("Fetching listing page %s", page_url)

            try:
                html = self.client.fetch(
                    page_url,
                    validator=page_has_listing_cards if self.config.browser_fallback else None,
                    wait_selectors=[
                        ".search-result-cards article.card",
                        "article.card",
                        "search-result-cards-v3 .cards-v3__card",
                        ".cards-v3__card",
                    ],
                )
            except Exception as exc:
                self._register_error(page_url, f"listing_page_fetch_failed: {exc}")
                if self.config.stop_on_error:
                    raise
                break

            self._pages_scanned += 1

            if known_total_pages is None:
                known_total_pages = parse_total_pages(html)
                if known_total_pages:
                    LOGGER.info("Detected %s listing pages", known_total_pages)

            cards = parse_listing_cards(html, page_url)
            if not cards:
                if self.config.save_debug_html or self.config.debug:
                    self._save_debug_html(f"listing_page_{page_number}", html)
                empty_pages_in_row += 1
                LOGGER.warning("No listing cards found on page %s", page_number)
                if (
                    not self.config.browser_fallback
                    and any(marker in html for marker in ("__NEXT_DATA__", "ng-version", "search-result"))
                ):
                    LOGGER.warning(
                        "HTML looks browser-rendered or hydrated. Try rerunning with --browser-fallback."
                    )
                if empty_pages_in_row >= 1:
                    break
            else:
                empty_pages_in_row = 0
                for card in cards:
                    cards_by_url.setdefault(card.url, card)

            if not self.config.all_pages and page_number >= self.config.max_pages:
                break
            page_number += 1

        return list(cards_by_url.values())

    def _collect_listing_details(self, cards: list[ListingCard]) -> list[ListingRecord]:
        records: list[ListingRecord] = []

        for index, card in enumerate(cards, start=1):
            LOGGER.info("Fetching listing %s/%s: %s", index, len(cards), card.url)
            try:
                html = self.client.fetch(
                    card.url,
                    validator=listing_page_has_main_content if self.config.browser_fallback else None,
                    wait_selectors=[".listing-page", ".listing-title", "h1"],
                )
            except Exception as exc:
                self._register_error(card.url, f"listing_fetch_failed: {exc}")
                if self.config.stop_on_error:
                    raise
                records.append(
                    ListingRecord(
                        listing_id=card.listing_id,
                        url=card.url,
                        title=card.address,
                        price_total=card.price_total,
                        price_total_raw=card.price_total_raw,
                        price_total_value=card.price_total_value,
                        area_m2=card.area_m2,
                        area_m2_raw=card.area_m2_raw,
                        area_m2_value=card.area_m2_value,
                        address=card.address,
                        seller_name=card.seller_name,
                        source_start_url=self.config.start_url,
                        scraped_at=utcnow_iso(),
                        parse_error=f"listing_fetch_failed: {exc}",
                        card=card.to_dict(),
                    )
                )
                continue

            try:
                details = parse_listing_details(
                    html,
                    url=card.url,
                    source_start_url=self.config.start_url,
                    card=card,
                )
                record = ListingRecord(**details.to_dict(), card=card.to_dict())
                self._enrich_record_with_metro(record)
                records.append(record)
            except Exception as exc:
                self._register_error(card.url, f"listing_parse_failed: {exc}")
                if self.config.save_debug_html or self.config.debug:
                    self._save_debug_html(f"listing_details_{card.listing_id or index}", html)
                if self.config.stop_on_error:
                    raise
                fallback_record = ListingRecord(
                    listing_id=card.listing_id,
                    url=card.url,
                    title=card.address,
                    price_total=card.price_total,
                    price_total_raw=card.price_total_raw,
                    price_total_value=card.price_total_value,
                    area_m2=card.area_m2,
                    area_m2_raw=card.area_m2_raw,
                    area_m2_value=card.area_m2_value,
                    address=card.address,
                    seller_name=card.seller_name,
                    source_start_url=self.config.start_url,
                    scraped_at=utcnow_iso(),
                    parse_error=str(exc),
                    card=card.to_dict(),
                )
                records.append(fallback_record)

        return records

    def _enrich_record_with_metro(self, record: ListingRecord) -> None:
        if not self.config.enable_poi_enrichment:
            return

        nearest_metro = self.poi_service.find_nearest_poi(
            lat=record.latitude,
            lon=record.longitude,
            category=POICategory.METRO_STATION,
            path=self.config.metro_data_path,
        )
        if nearest_metro is None:
            return

        record.nearest_metro_station_id = nearest_metro.poi.id
        record.nearest_metro_station_name = nearest_metro.poi.name
        record.nearest_metro_distance_meters = round(nearest_metro.distance_meters, 1)
        record.nearest_metro_walking_minutes = round(
            nearest_metro.walking_minutes_estimate,
            1,
        )
        record.metro_score = score_metro_walking_minutes(
            nearest_metro.walking_minutes_estimate
        )

    def _register_error(self, url: str, message: str) -> None:
        LOGGER.error("%s | %s", url, message)
        self._errors.append({"url": url, "error": message, "timestamp": utcnow_iso()})

    def _save_debug_html(self, name: str, html: str) -> None:
        path = Path(self.config.debug_dir) / f"{name}.html"
        save_text(path, html)
        LOGGER.info("Saved debug HTML to %s", path)

    def close(self) -> None:
        self.client.close()
