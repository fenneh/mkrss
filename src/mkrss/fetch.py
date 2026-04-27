import asyncio
import logging
from contextlib import suppress

import httpx

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "mkrss/0.1 (+https://mkrss.local)"
HTTP_TIMEOUT = 15.0
BROWSER_TIMEOUT_MS = 25000
BROWSER_CONCURRENCY = 2


class Fetcher:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None
        self._playwright = None
        self._browser = None
        self._browser_lock = asyncio.Lock()
        self._browser_sem = asyncio.Semaphore(BROWSER_CONCURRENCY)

    async def start(self) -> None:
        self._http = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        )

    async def stop(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None
        if self._browser is not None:
            with suppress(Exception):
                await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            with suppress(Exception):
                await self._playwright.stop()
            self._playwright = None

    async def _ensure_browser(self):
        if self._browser is not None:
            return self._browser
        async with self._browser_lock:
            if self._browser is None:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    async def fetch(
        self,
        url: str,
        *,
        render_mode: str,
        user_agent: str | None = None,
        encoding: str | None = None,
    ) -> str:
        if render_mode == "browser":
            return await self._fetch_browser(url, user_agent=user_agent)
        return await self._fetch_http(url, user_agent=user_agent, encoding=encoding)

    async def _fetch_http(self, url: str, *, user_agent: str | None, encoding: str | None) -> str:
        assert self._http is not None, "Fetcher.start() not called"
        headers: dict[str, str] = {}
        if user_agent:
            headers["User-Agent"] = user_agent
        resp = await self._http.get(url, headers=headers or None)
        resp.raise_for_status()
        if encoding:
            return resp.content.decode(encoding, errors="replace")
        return resp.text

    async def _fetch_browser(self, url: str, *, user_agent: str | None) -> str:
        browser = await self._ensure_browser()
        async with self._browser_sem:
            context = await browser.new_context(
                user_agent=user_agent or DEFAULT_USER_AGENT,
                ignore_https_errors=True,
            )
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=BROWSER_TIMEOUT_MS)
                return await page.content()
            finally:
                with suppress(Exception):
                    await context.close()
