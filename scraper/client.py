from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .browser_fallback import PlaywrightFallbackClient
from .config import ScraperConfig
from .storage import save_text

LOGGER = logging.getLogger(__name__)


class FetchError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, config: ScraperConfig) -> None:
        self.config = config
        self.session = requests.Session()
        retry = Retry(
            total=config.retry_total,
            backoff_factor=config.retry_backoff_factor,
            status_forcelist=list(config.retry_statuses),
            allowed_methods=["GET", "HEAD"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(config.headers)
        self._browser: PlaywrightFallbackClient | None = None
        self._last_request_at = 0.0

    def _respect_delay(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.config.delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _requests_fetch(self, url: str) -> str:
        self._respect_delay()
        response = self.session.get(url, timeout=self.config.timeout)
        self._last_request_at = time.monotonic()
        if response.status_code >= 400:
            raise FetchError(f"HTTP {response.status_code} for {url}")
        return response.text

    def _requests_fetch_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self._respect_delay()
        merged_headers = {"Accept": "application/json, text/plain, */*"}
        if headers:
            merged_headers.update(headers)
        response = self.session.get(url, timeout=self.config.timeout, headers=merged_headers)
        self._last_request_at = time.monotonic()
        if response.status_code >= 400:
            raise FetchError(f"HTTP {response.status_code} for {url}")
        try:
            return response.json()
        except ValueError as exc:
            raise FetchError(f"Invalid JSON response for {url}") from exc

    def bootstrap_listing_api(self, start_url: str) -> dict[str, str]:
        html = self._requests_fetch(start_url)

        token_match = re.search(
            r'<meta\s+name="api-token"\s+content="([^"]+)"',
            html,
            re.IGNORECASE,
        )
        api_token = token_match.group(1) if token_match else None

        cuid = self.session.cookies.get("user_id") or self.session.cookies.get("ota-cuid")
        headers: dict[str, str] = {"Referer": start_url}
        if api_token:
            headers["ota-token"] = api_token
        if cuid:
            headers["ota-cuid"] = cuid
        headers["ota-loaded"] = str(int(time.time()))
        return headers

    def _browser_fetch(self, url: str, wait_selectors: list[str] | None = None) -> str:
        if not self.config.browser_fallback:
            raise FetchError(f"Browser fallback disabled and requests failed for {url}")
        if self._browser is None:
            self._browser = PlaywrightFallbackClient(timeout_ms=int(self.config.timeout * 1000))
        LOGGER.info("Using browser fallback for %s", url)
        return self._browser.fetch(url, wait_selectors=wait_selectors or [])

    def fetch(
        self,
        url: str,
        validator: Callable[[str], bool] | None = None,
        wait_selectors: list[str] | None = None,
    ) -> str:
        last_error: Exception | None = None
        try:
            html = self._requests_fetch(url)
            if validator is None or validator(html):
                return html
            self._save_debug_html("requests_invalid", url, html)
            LOGGER.warning("Validator rejected requests HTML for %s", url)
            last_error = FetchError(f"Validator rejected requests HTML for {url}")
        except Exception as exc:
            LOGGER.warning("Requests fetch failed for %s: %s", url, exc)
            last_error = exc

        if self.config.browser_fallback:
            try:
                html = self._browser_fetch(url, wait_selectors=wait_selectors)
                if validator is None or validator(html):
                    return html
                self._save_debug_html("browser_invalid", url, html)
                raise FetchError(f"Validator rejected browser HTML for {url}")
            except Exception as exc:
                last_error = exc

        raise FetchError(str(last_error) if last_error else f"Failed to fetch {url}")

    def close(self) -> None:
        self.session.close()
        if self._browser is not None:
            self._browser.close()

    def fetch_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._requests_fetch_json(url, headers=headers)

    def _save_debug_html(self, prefix: str, url: str, html: str) -> None:
        if not (self.config.save_debug_html or self.config.debug):
            return
        listing_id = "".join(ch for ch in url if ch.isdigit())[-12:] or "page"
        path = Path(self.config.debug_dir) / f"{prefix}_{listing_id}.html"
        save_text(path, html)
        LOGGER.info("Saved debug HTML to %s", path)
