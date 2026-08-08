from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from mkrss.fetch import DEFAULT_USER_AGENT, Fetcher


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    fetcher = Fetcher()
    await fetcher.start()
    assert fetcher._http is not None
    await fetcher.stop()
    assert fetcher._http is None


@pytest.mark.asyncio
async def test_stop_without_start_is_a_noop():
    fetcher = Fetcher()
    await fetcher.stop()


@pytest.mark.asyncio
async def test_fetch_http_returns_text():
    def handler(request):
        return httpx.Response(200, text="<html>ok</html>")

    fetcher = Fetcher()
    fetcher._http = _client_for(handler)

    result = await fetcher.fetch("https://example.com", render_mode="http")

    assert result == "<html>ok</html>"


@pytest.mark.asyncio
async def test_fetch_http_uses_default_user_agent():
    seen = {}

    def handler(request):
        seen["user_agent"] = request.headers.get("user-agent")
        return httpx.Response(200, text="ok")

    fetcher = Fetcher()
    fetcher._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )

    await fetcher.fetch("https://example.com", render_mode="http")

    assert seen["user_agent"] == DEFAULT_USER_AGENT


@pytest.mark.asyncio
async def test_fetch_http_overrides_user_agent():
    seen = {}

    def handler(request):
        seen["user_agent"] = request.headers.get("user-agent")
        return httpx.Response(200, text="ok")

    fetcher = Fetcher()
    fetcher._http = _client_for(handler)

    await fetcher.fetch("https://example.com", render_mode="http", user_agent="custom-agent")

    assert seen["user_agent"] == "custom-agent"


@pytest.mark.asyncio
async def test_fetch_http_decodes_with_encoding():
    def handler(request):
        return httpx.Response(200, content="café".encode("latin-1"))

    fetcher = Fetcher()
    fetcher._http = _client_for(handler)

    result = await fetcher.fetch("https://example.com", render_mode="http", encoding="latin-1")

    assert result == "café"


@pytest.mark.asyncio
async def test_fetch_http_raises_on_error_status():
    def handler(request):
        return httpx.Response(404, text="not found")

    fetcher = Fetcher()
    fetcher._http = _client_for(handler)

    with pytest.raises(httpx.HTTPStatusError):
        await fetcher.fetch("https://example.com", render_mode="http")


@pytest.mark.asyncio
async def test_ensure_browser_launches_once(monkeypatch):
    launched = []

    fake_browser = MagicMock()
    fake_playwright_instance = MagicMock()
    fake_playwright_instance.chromium.launch = AsyncMock(
        side_effect=lambda **kw: launched.append(kw) or fake_browser
    )
    fake_playwright_start = AsyncMock(return_value=fake_playwright_instance)

    fake_async_playwright = MagicMock()
    fake_async_playwright.return_value.start = fake_playwright_start

    import mkrss.fetch as fetch_module

    monkeypatch.setattr(
        "playwright.async_api.async_playwright",
        fake_async_playwright,
        raising=False,
    )

    fetcher = fetch_module.Fetcher()
    browser1 = await fetcher._ensure_browser()
    browser2 = await fetcher._ensure_browser()

    assert browser1 is fake_browser
    assert browser2 is fake_browser
    assert len(launched) == 1


@pytest.mark.asyncio
async def test_fetch_browser_mode_returns_page_content(monkeypatch):
    fake_page = MagicMock()
    fake_page.goto = AsyncMock()
    fake_page.content = AsyncMock(return_value="<html>rendered</html>")

    fake_context = MagicMock()
    fake_context.new_page = AsyncMock(return_value=fake_page)
    fake_context.close = AsyncMock()

    fake_browser = MagicMock()
    fake_browser.new_context = AsyncMock(return_value=fake_context)

    fetcher = Fetcher()
    monkeypatch.setattr(fetcher, "_ensure_browser", AsyncMock(return_value=fake_browser))

    result = await fetcher.fetch("https://example.com", render_mode="browser")

    assert result == "<html>rendered</html>"
    fake_page.goto.assert_awaited_once()
    fake_context.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_suppresses_browser_close_errors():
    fetcher = Fetcher()
    fetcher._browser = MagicMock()
    fetcher._browser.close = AsyncMock(side_effect=RuntimeError("already closed"))
    fetcher._playwright = MagicMock()
    fetcher._playwright.stop = AsyncMock(side_effect=RuntimeError("already stopped"))

    await fetcher.stop()

    assert fetcher._browser is None
    assert fetcher._playwright is None
