from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36 OikotieScraper/1.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


@dataclass(slots=True)
class ScraperConfig:
    start_url: str
    max_pages: int = 30
    all_pages: bool = False
    page_size: int = 24
    delay: float = 1.0
    timeout: float = 20.0
    output_path: Path = Path("data/listings_latest.json")
    state_file: Path = Path("data/state.json")
    history_dir: Path = Path("data/runs")
    browser_fallback: bool = False
    debug: bool = False
    stop_on_error: bool = False
    save_debug_html: bool = False
    debug_dir: Path = Path("data/debug")
    retry_total: int = 3
    retry_backoff_factor: float = 1.0
    retry_statuses: tuple[int, ...] = (403, 429, 500, 502, 503, 504)
    enable_poi_enrichment: bool = True
    poi_data_dir: Path = Path("data/poi")
    metro_data_path: Path = Path("data/poi/metro_stations.json")
    walking_detour_factor: float = 1.2
    walking_speed_m_per_min: float = 80.0
    headers: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HEADERS))
