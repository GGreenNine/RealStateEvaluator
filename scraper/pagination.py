from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def build_page_url(start_url: str, page_number: int) -> str:
    parts = urlsplit(start_url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query_items = [(key, value) for key, value in query_items if key != "pagination"]
    query_items.append(("pagination", str(page_number)))
    query = urlencode(query_items, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def build_search_api_url(start_url: str, page_number: int, page_size: int) -> str:
    parts = urlsplit(start_url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query_items = [
        (key, value)
        for key, value in query_items
        if key not in {"pagination", "limit", "offset", "sortBy"}
    ]
    query_items.append(("limit", str(page_size)))
    query_items.append(("offset", str((page_number - 1) * page_size)))
    query_items.append(("sortBy", "published_sort_desc"))
    query = urlencode(query_items, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, "/api/search", query, ""))
