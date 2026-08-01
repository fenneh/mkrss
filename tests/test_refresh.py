import sqlite3
from pathlib import Path

import pytest

from mkrss import db, refresh
from mkrss.fetch import Fetcher
from mkrss.models import Feed, FeedField
from mkrss.refresh import refresh_one, tick

FIXTURE = Path(__file__).parent / "fixtures" / "aisi_blog.html"
POST_FIXTURE = Path(__file__).parent / "fixtures" / "aisi_post.html"


class StubFetcher(Fetcher):
    def __init__(self, html: str) -> None:
        self._html = html

    async def fetch(self, url, *, render_mode, user_agent=None, encoding=None):
        return self._html


class FailingFetcher(Fetcher):
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def fetch(self, url, *, render_mode, user_agent=None, encoding=None):
        raise self._error


class ByUrlFetcher(Fetcher):
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages

    async def fetch(self, url, *, render_mode, user_agent=None, encoding=None):
        return self._pages[url]


def _new_feed(**overrides) -> Feed:
    base = Feed(
        id=0,
        slug="aisi-test",
        source_url="https://www.aisi.gov.uk/blog",
        title="AISI",
        description="",
        link="https://www.aisi.gov.uk/blog",
        extraction_mode="css",
        render_mode="http",
        item_selector="div.work-card-wrapper.w-dyn-item",
        global_pattern=None,
        item_pattern=None,
        reverse_order=False,
        title_template="{title}",
        link_template="{link}",
        description_template="<p>{description}</p>",
        refresh_minutes=30,
        user_agent=None,
        encoding=None,
        last_fetched_at=None,
        last_status=None,
        last_error=None,
        last_item_count=None,
        created_at="",
        updated_at="",
        fields=[
            FeedField(name="link", selector='a[href*="/blog/"]', attribute="href", transform="absolute_url"),
            FeedField(name="title", selector='[fs-list-field="title"]'),
            FeedField(name="category", selector='[fs-list-field="category"]'),
            FeedField(name="date", selector='[fs-list-field="date"]'),
            FeedField(name="description", selector='[fs-list-field="description"]'),
        ],
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _setup(tmp_path) -> sqlite3.Connection:
    conn = db.connect(str(tmp_path / "t.sqlite3"))
    db.migrate(conn)
    return conn


@pytest.mark.asyncio
async def test_refresh_fetch_failure_marks_error(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _new_feed())
    fetcher = FailingFetcher(RuntimeError("boom"))

    await refresh_one(conn, fetcher, feed_id)

    saved = db.get_feed_by_id(conn, feed_id)
    assert saved.last_status == "error"
    assert saved.last_error == "fetch: boom"
    assert saved.last_item_count is None


@pytest.mark.asyncio
async def test_refresh_extract_failure_marks_error(tmp_path, monkeypatch):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _new_feed())
    fetcher = StubFetcher(FIXTURE.read_text())

    def _boom(feed, html):
        raise ValueError("bad selector")

    monkeypatch.setattr(refresh, "extract", _boom)
    await refresh_one(conn, fetcher, feed_id)

    saved = db.get_feed_by_id(conn, feed_id)
    assert saved.last_status == "error"
    assert saved.last_error == "extract: bad selector"


@pytest.mark.asyncio
async def test_refresh_skips_item_with_broken_link_template(tmp_path):
    conn = _setup(tmp_path)
    feed = _new_feed(link_template="{missing_field}")
    feed_id = db.insert_feed(conn, feed)
    fetcher = StubFetcher(FIXTURE.read_text())

    await refresh_one(conn, fetcher, feed_id)

    items = db.list_items(conn, feed_id)
    assert items == []
    saved = db.get_feed_by_id(conn, feed_id)
    assert saved.last_status == "error"
    assert "items skipped" in saved.last_error


@pytest.mark.asyncio
async def test_refresh_enriches_post_source_fields(tmp_path):
    conn = _setup(tmp_path)
    feed = _new_feed(
        fields=[
            FeedField(name="link", selector='a[href*="/blog/"]', attribute="href", transform="absolute_url"),
            FeedField(name="title", selector='[fs-list-field="title"]'),
            FeedField(name="body", selector="article", source="post"),
        ]
    )
    fetcher = ByUrlFetcher(
        {
            "https://www.aisi.gov.uk/blog": FIXTURE.read_text(),
            "https://www.aisi.gov.uk/blog/first-post": POST_FIXTURE.read_text(),
            "https://www.aisi.gov.uk/blog/second-post": POST_FIXTURE.read_text(),
        }
    )
    feed_id = db.insert_feed(conn, feed)

    await refresh_one(conn, fetcher, feed_id)

    items = db.list_items(conn, feed_id)
    assert len(items) == 2
    assert all("body" in i.raw_fields_json for i in items)


@pytest.mark.asyncio
async def test_tick_refreshes_only_due_feeds(tmp_path):
    conn = _setup(tmp_path)
    due_id = db.insert_feed(conn, _new_feed(slug="due"))
    not_due_id = db.insert_feed(conn, _new_feed(slug="not-due"))
    db.update_feed_status(conn, not_due_id, status="ok", error=None, item_count=0)
    conn.execute(
        "UPDATE feeds SET refresh_minutes = 999999 WHERE id = ?",
        (not_due_id,),
    )
    fetcher = StubFetcher(FIXTURE.read_text())

    await tick(conn, fetcher)

    assert db.get_feed_by_id(conn, due_id).last_status == "ok"
    assert db.get_feed_by_id(conn, not_due_id).last_item_count == 0


@pytest.mark.asyncio
async def test_tick_continues_after_one_feed_errors(tmp_path, monkeypatch):
    conn = _setup(tmp_path)
    bad_id = db.insert_feed(conn, _new_feed(slug="bad"))
    good_id = db.insert_feed(conn, _new_feed(slug="good"))
    fetcher = StubFetcher(FIXTURE.read_text())

    real_refresh_one = refresh.refresh_one

    async def _flaky(conn, fetcher, feed_id):
        if feed_id == bad_id:
            raise RuntimeError("unexpected")
        await real_refresh_one(conn, fetcher, feed_id)

    monkeypatch.setattr(refresh, "refresh_one", _flaky)
    await tick(conn, fetcher)

    assert db.get_feed_by_id(conn, good_id).last_status == "ok"
