from __future__ import annotations

import logging
from typing import Iterable

LOGGER = logging.getLogger(__name__)


class PlaywrightFallbackClient:
    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._context = None

    def _ensure_context(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Install it with 'pip install playwright' "
                "and run 'python -m playwright install chromium'."
            ) from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(locale="fi-FI")

    def fetch(self, url: str, wait_selectors: Iterable[str] | None = None) -> str:
        self._ensure_context()
        assert self._context is not None

        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            self._dismiss_banners(page)
            if wait_selectors:
                for selector in wait_selectors:
                    try:
                        page.wait_for_selector(selector, timeout=3000)
                        break
                    except Exception:
                        continue
            page.wait_for_timeout(1200)
            return page.content()
        finally:
            page.close()

    def _dismiss_banners(self, page) -> None:
        selectors = [
            'button:has-text("Hyv\u00e4ksy")',
            'button:has-text("Accept")',
            'button:has-text("OK")',
            '[aria-label="Close"]',
            'button[aria-label="Sulje"]',
        ]
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=800):
                    locator.click(timeout=800)
                    LOGGER.debug("Dismissed banner with selector %s", selector)
                    return
            except Exception:
                continue

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
