from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .models import ListingCard, ListingDetails
from .utils import (
    PAGE_MARKER_RE,
    join_non_empty,
    normalize_area,
    normalize_floor,
    normalize_land_ownership,
    normalize_listing_id,
    normalize_monthly_fee,
    normalize_price,
    normalize_price_per_m2,
    normalize_text,
    utcnow_iso,
)

LOGGER = logging.getLogger(__name__)

CARD_SELECTORS = {
    "container": (
        ".search-result-cards article.card, "
        "article.card, "
        "search-result-cards-v3 .cards-v3__card, "
        ".cards-v3__card"
    ),
    "link": "a.card__link, a.ot-card-v3",
    "address": ".card__address, .card-v3-text-container__text",
    "price": ".card__price, .card-v3-text-container__key-details .heading",
    "meta": ".card__meta, .card-v3-text-container__details",
    "seller": ".card__seller, .ot-card-v3-realtor__name",
}

DETAIL_SELECTORS: dict[str, list[str]] = {
    "title": [".listing-title", "h1"],
    "price_total": [".listing-price-total", '.field[data-name="price_total"] .field-value'],
    "price_per_m2": [
        ".listing-price-per-m2",
        '.field[data-name="price_per_m2"] .field-value',
    ],
    "area_m2": [".listing-area", '.field[data-name="area_m2"] .field-value'],
    "address": [".listing-address", '.field[data-name="address"] .field-value'],
    "district": [".listing-district", '.field[data-name="district"] .field-value'],
    "city": [".listing-city"],
    "floor": [".listing-floor", '.field[data-name="floor"] .field-value'],
    "building_year": [
        ".listing-building-year",
        '.field[data-name="building_year"] .field-value',
    ],
    "listing_overview": [".listing-overview"],
    "building_type": [".listing-building-type"],
    "description": [".listing-description"],
    "planned_repairs": ['.field[data-name="planned_repairs"] .field-value'],
    "completed_repairs": ['.field[data-name="completed_repairs"] .field-value'],
    "maintenance_fee": ['.field[data-name="maintenance_fee"] .field-value'],
    "water_fee": ['.field[data-name="water_fee"] .field-value'],
    "sauna_fee": ['.field[data-name="sauna_fee"] .field-value'],
    "parking_fee": ['.field[data-name="parking_fee"] .field-value'],
    "land_ownership": ['.field[data-name="land_ownership"] .field-value'],
    "seller_name": [".card__seller", ".listing-seller", ".seller-info__name"],
}

LABEL_FALLBACKS = {
    "maintenance_fee": ["Hoitovastike", "Yhti\u00f6vastike", "Vastike"],
    "water_fee": ["Vesimaksu"],
    "sauna_fee": ["Saunamaksu"],
    "parking_fee": ["Autopaikkamaksu", "Pys\u00e4k\u00f6intimaksu"],
    "building_year": ["Rakennusvuosi", "Valmistumisvuosi"],
    "land_ownership": ["Tontin omistus", "Tontti"],
    "planned_repairs": ["Tulevat remontit", "Suunnitellut remontit"],
    "completed_repairs": ["Tehdyt remontit", "Kunnossapitotarveselvitys"],
    "district": ["Kaupunginosa", "Alue"],
    "floor": ["Kerros"],
    "rooms": ["Huoneita", "Huoneluku"],
    "building_type": ["Rakennustyyppi", "Talotyyppi"],
}


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def extract_text_or_none(node: Tag | None) -> str | None:
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return normalize_text(text)


def extract_html_text_or_none(node: Tag | None) -> str | None:
    if node is None:
        return None
    parts = [normalize_text(part) for part in node.stripped_strings]
    filtered = [part for part in parts if part]
    if not filtered:
        return None
    return "\n".join(filtered)


def extract_first_by_selectors(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        value = extract_html_text_or_none(node)
        if value:
            return value
    return None


def extract_field_by_data_name(soup: BeautifulSoup, field_name: str) -> str | None:
    selector = f'.field[data-name="{field_name}"] .field-value'
    return extract_first_by_selectors(soup, [selector])


def find_value_near_label(soup: BeautifulSoup, labels: list[str]) -> str | None:
    for label in labels:
        text_node = soup.find(
            string=lambda value: isinstance(value, str) and label.lower() in value.lower()
        )
        if not text_node:
            continue
        parent = text_node.parent if isinstance(text_node.parent, Tag) else None
        if parent is None:
            continue

        next_sibling = parent.find_next_sibling()
        value = extract_html_text_or_none(next_sibling if isinstance(next_sibling, Tag) else None)
        if value and value.lower() != normalize_text(label).lower():
            return value

        for selector in ("dd", ".value", ".field-value"):
            candidate = parent.find_next(selector)
            value = extract_html_text_or_none(candidate if isinstance(candidate, Tag) else None)
            if value and value.lower() != normalize_text(label).lower():
                return value

        parent_text = extract_html_text_or_none(parent)
        if parent_text and ":" in parent_text:
            left, _, right = parent_text.partition(":")
            if label.lower() in left.lower():
                right_value = normalize_text(right)
                if right_value:
                    return right_value
    return None


def find_info_table_value(soup: BeautifulSoup, labels: list[str]) -> str | None:
    normalized_labels = {normalize_text(label).lower() for label in labels if normalize_text(label)}
    if not normalized_labels:
        return None

    for row in soup.select(".info-table__row"):
        if not isinstance(row, Tag):
            continue
        title_node = row.select_one(".info-table__title")
        value_node = row.select_one(".info-table__value")
        title = extract_text_or_none(title_node if isinstance(title_node, Tag) else None)
        if not title or title.lower() not in normalized_labels:
            continue
        value = extract_html_text_or_none(value_node if isinstance(value_node, Tag) else None)
        if value:
            return value
    return None


def parse_total_pages(html: str) -> int | None:
    soup = make_soup(html)
    text = extract_html_text_or_none(soup.select_one(".search-result-controls")) or ""
    match = PAGE_MARKER_RE.search(text)
    if match:
        return int(match.group(2))

    generic_match = re.search(r"\b(\d+)\s*/\s*(\d+)\b", text)
    if generic_match:
        return int(generic_match.group(2))

    page_numbers: list[int] = []
    for node in soup.select(".pagination button, .pagination a, nav[aria-label*=Pagination] button"):
        value = extract_text_or_none(node)
        if value and value.isdigit():
            page_numbers.append(int(value))
    if page_numbers:
        return max(page_numbers)
    return None


def page_has_listing_cards(html: str) -> bool:
    soup = make_soup(html)
    return bool(soup.select(CARD_SELECTORS["container"]))


def listing_page_has_main_content(html: str) -> bool:
    soup = make_soup(html)
    return bool(soup.select_one(".listing-title, h1"))


def parse_rooms_from_meta(meta: str | None) -> str | None:
    if not meta:
        return None
    match = re.search(r"Huoneita\s*([^\s\u00b7]+)", meta, re.IGNORECASE)
    if match:
        return normalize_text(match.group(1))
    match = re.search(r"Rooms?\s*([^\s\u00b7]+)", meta, re.IGNORECASE)
    if match:
        return normalize_text(match.group(1))
    match = re.search(r"(\d+\s*h(?:\+\w+)?)", meta, re.IGNORECASE)
    if match:
        return normalize_text(match.group(1))
    return None


def parse_area_from_meta(meta: str | None) -> tuple[str | None, float | None]:
    if not meta:
        return None, None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*m(?:\u00b2|2)", meta, re.IGNORECASE)
    if not match:
        return None, None
    raw = f"{match.group(1)} m\u00b2"
    return raw, normalize_area(raw)


def parse_building_type_from_meta(meta: str | None) -> str | None:
    if not meta:
        return None
    parts = [normalize_text(part) for part in meta.split("\u00b7")]
    for part in parts:
        if not part:
            continue
        lowered = part.lower()
        if any(
            token in lowered
            for token in (
                "kerrostalo",
                "rivitalo",
                "paritalo",
                "omakotitalo",
                "apartment building",
                "terraced house",
                "semi-detached",
            )
        ):
            return part
    return None


def parse_listing_cards(html: str, page_url: str) -> list[ListingCard]:
    soup = make_soup(html)
    cards: list[ListingCard] = []
    seen_urls: set[str] = set()

    for card_node in soup.select(CARD_SELECTORS["container"]):
        link_node = card_node.select_one(CARD_SELECTORS["link"])
        href = link_node.get("href") if isinstance(link_node, Tag) else None
        if not href:
            continue
        url = urljoin(page_url, href)
        if "/myytavat-asunnot/" not in url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        address = extract_text_or_none(card_node.select_one(".card__address"))
        if not address:
            address_nodes = card_node.select(".card-v3-text-container__text")
            if address_nodes:
                address = extract_text_or_none(address_nodes[0] if isinstance(address_nodes[0], Tag) else None)

        price_raw = extract_text_or_none(card_node.select_one(".card__price"))
        area_raw = None
        area_value = None
        if not price_raw:
            key_details = card_node.select(".card-v3-text-container__key-details .heading")
            if key_details:
                price_raw = extract_text_or_none(key_details[0] if isinstance(key_details[0], Tag) else None)
            if len(key_details) > 1:
                area_raw = extract_text_or_none(key_details[1] if isinstance(key_details[1], Tag) else None)
                area_value = normalize_area(area_raw)

        meta_raw = extract_text_or_none(card_node.select_one(".card__meta"))
        if not meta_raw:
            details_parts = [
                extract_text_or_none(node)
                for node in card_node.select(".card-v3-text-container__details .card-v3-text-container__text")
            ]
            details_parts = [part for part in details_parts if part]
            meta_raw = " · ".join(details_parts) if details_parts else None

        seller_name = extract_text_or_none(card_node.select_one(CARD_SELECTORS["seller"]))
        if area_raw is None:
            area_raw, area_value = parse_area_from_meta(meta_raw)

        cards.append(
            ListingCard(
                url=url,
                listing_id=normalize_listing_id(url),
                address=address,
                price_total=price_raw,
                price_total_raw=price_raw,
                price_total_value=normalize_price(price_raw),
                area_m2=area_raw,
                area_m2_raw=area_raw,
                area_m2_value=area_value,
                rooms=parse_rooms_from_meta(meta_raw),
                seller_name=seller_name,
                meta_raw=meta_raw,
            )
        )
    return cards


def parse_listing_cards_from_api(payload: dict[str, Any]) -> list[ListingCard]:
    cards: list[ListingCard] = []
    for item in payload.get("cards", []):
        if not isinstance(item, dict):
            continue
        url = normalize_text(item.get("url"))
        if not url:
            continue

        data = item.get("data") or {}
        location = item.get("location") or {}
        company = item.get("company") or {}

        street = normalize_text(location.get("address"))
        district = normalize_text(location.get("district"))
        city = normalize_text(location.get("city"))
        address = join_non_empty([street, district, city])

        price_raw = normalize_text(data.get("price"))
        area_raw = normalize_text(data.get("size"))

        floor = data.get("floor")
        floor_total = data.get("buildingFloorCount")
        build_year = data.get("buildYear")
        meta_parts = [
            f"Rooms {data['rooms']}" if data.get("rooms") is not None else None,
            f"Floor {floor}/{floor_total}" if floor is not None and floor_total is not None else None,
            str(build_year) if build_year is not None else None,
        ]
        meta_raw = " · ".join(part for part in meta_parts if part) or None

        rooms_value = data.get("rooms")
        rooms = str(rooms_value) if rooms_value is not None else None

        cards.append(
            ListingCard(
                url=url,
                listing_id=str(item.get("cardId")) if item.get("cardId") is not None else normalize_listing_id(url),
                address=address,
                price_total=price_raw,
                price_total_raw=price_raw,
                price_total_value=normalize_price(price_raw),
                area_m2=area_raw,
                area_m2_raw=area_raw,
                area_m2_value=normalize_area(area_raw),
                rooms=rooms,
                seller_name=normalize_text(company.get("realtorName")),
                meta_raw=meta_raw,
            )
        )
    return cards


def parse_json_ld_candidates(soup: BeautifulSoup) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for node in soup.select('script[type="application/ld+json"]'):
        raw = node.string or node.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            candidates.extend(item for item in payload if isinstance(item, dict))
        elif isinstance(payload, dict):
            graph = payload.get("@graph")
            if isinstance(graph, list):
                candidates.extend(item for item in graph if isinstance(item, dict))
            candidates.append(payload)
    return candidates


def pick_json_ld_value(candidates: list[dict[str, Any]], *keys: str) -> Any:
    for candidate in candidates:
        for key in keys:
            value = candidate.get(key)
            if value:
                return value
            address = candidate.get("address")
            if isinstance(address, dict) and key in address and address[key]:
                return address[key]
            offers = candidate.get("offers")
            if isinstance(offers, dict) and key in offers and offers[key]:
                return offers[key]
    return None


def infer_city_from_address(address: str | None, title: str | None) -> str | None:
    source = address or title
    text = normalize_text(source)
    if not text:
        return None
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        return None
    last = parts[-1]
    postcode_split = re.sub(r"^\d{5}\s+", "", last).strip()
    return postcode_split or None


def infer_district_from_title(title: str | None) -> str | None:
    text = normalize_text(title)
    if not text or "," not in text:
        return None
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) >= 3:
        return parts[-2]
    return None


def parse_listing_details(
    html: str,
    url: str,
    source_start_url: str | None = None,
    card: ListingCard | None = None,
) -> ListingDetails:
    soup = make_soup(html)
    json_ld = parse_json_ld_candidates(soup)

    def field(name: str) -> str | None:
        value = extract_first_by_selectors(soup, DETAIL_SELECTORS.get(name, []))
        if value:
            return value
        value = extract_field_by_data_name(soup, name)
        if value:
            return value
        value = find_info_table_value(soup, LABEL_FALLBACKS.get(name, []))
        if value:
            return value
        value = find_value_near_label(soup, LABEL_FALLBACKS.get(name, []))
        if value:
            return value
        if name == "title":
            return normalize_text(pick_json_ld_value(json_ld, "name", "headline"))
        if name == "description":
            return normalize_text(pick_json_ld_value(json_ld, "description"))
        return None

    title = field("title")
    price_total_raw = field("price_total")
    json_ld_price = pick_json_ld_value(json_ld, "price")
    if not price_total_raw and json_ld_price is not None:
        price_total_raw = normalize_text(str(json_ld_price))

    price_per_m2_raw = field("price_per_m2")
    area_m2_raw = field("area_m2")
    address = field("address")
    district = field("district")
    city = field("city")
    floor_raw = field("floor")
    building_year_raw = field("building_year")
    listing_overview = field("listing_overview")
    description = field("description")
    planned_repairs = field("planned_repairs")
    completed_repairs = field("completed_repairs")
    maintenance_fee_raw = field("maintenance_fee")
    water_fee_raw = field("water_fee")
    sauna_fee_raw = field("sauna_fee")
    parking_fee_raw = field("parking_fee")
    land_ownership_raw = field("land_ownership")
    seller_name = field("seller_name")
    rooms = field("rooms")
    building_type = field("building_type")

    if not address and card and card.address:
        address = card.address
    if not price_total_raw and card and card.price_total_raw:
        price_total_raw = card.price_total_raw
    if not area_m2_raw and card and card.area_m2_raw:
        area_m2_raw = card.area_m2_raw
    if not seller_name and card and card.seller_name:
        seller_name = card.seller_name
    if not rooms and card and card.rooms:
        rooms = card.rooms
    if not building_type and card and card.meta_raw:
        building_type = parse_building_type_from_meta(card.meta_raw)

    if not address:
        street = pick_json_ld_value(json_ld, "streetAddress")
        locality = pick_json_ld_value(json_ld, "addressLocality")
        address = join_non_empty([street, locality])

    city = city or infer_city_from_address(address, title)
    district = district or infer_district_from_title(title)
    floor_current, floor_total = normalize_floor(floor_raw)

    building_year = None
    if building_year_raw:
        year_match = re.search(r"(19|20)\d{2}", building_year_raw)
        if year_match:
            building_year = int(year_match.group(0))

    details = ListingDetails(
        listing_id=normalize_listing_id(url),
        url=url,
        title=title,
        price_total=price_total_raw,
        price_total_raw=price_total_raw,
        price_total_value=normalize_price(price_total_raw),
        price_per_m2=price_per_m2_raw,
        price_per_m2_raw=price_per_m2_raw,
        price_per_m2_value=normalize_price_per_m2(price_per_m2_raw),
        area_m2=area_m2_raw,
        area_m2_raw=area_m2_raw,
        area_m2_value=normalize_area(area_m2_raw),
        address=address,
        district=district,
        city=city,
        floor=floor_raw,
        floor_raw=floor_raw,
        floor_current=floor_current,
        floor_total=floor_total,
        building_year=building_year,
        listing_overview=listing_overview,
        description=description,
        planned_repairs=planned_repairs,
        completed_repairs=completed_repairs,
        maintenance_fee=maintenance_fee_raw,
        maintenance_fee_raw=maintenance_fee_raw,
        maintenance_fee_value=normalize_monthly_fee(maintenance_fee_raw),
        water_fee=water_fee_raw,
        water_fee_raw=water_fee_raw,
        water_fee_value=normalize_monthly_fee(water_fee_raw),
        sauna_fee=sauna_fee_raw,
        sauna_fee_raw=sauna_fee_raw,
        sauna_fee_value=normalize_monthly_fee(sauna_fee_raw),
        parking_fee=parking_fee_raw,
        parking_fee_raw=parking_fee_raw,
        parking_fee_value=normalize_monthly_fee(parking_fee_raw),
        land_ownership_raw=land_ownership_raw,
        land_ownership=land_ownership_raw,
        land_ownership_normalized=normalize_land_ownership(land_ownership_raw),
        rooms=rooms,
        building_type=building_type,
        seller_name=seller_name,
        source_start_url=source_start_url,
        scraped_at=utcnow_iso(),
    )

    missing_fields = [
        name
        for name in ("title", "price_total_raw", "area_m2_raw", "address")
        if getattr(details, name) is None
    ]
    if missing_fields:
        LOGGER.warning("Missing fields for %s: %s", url, ", ".join(missing_fields))

    return details
