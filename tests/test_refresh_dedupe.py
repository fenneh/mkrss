import sqlite3
from pathlib import Path

import pytest

from mkrss import db
from mkrss.fetch import Fetcher
from mkrss.models import Feed, FeedField
from mkrss.refresh import refresh_one

FIXTURE = Path(__file__).parent / "fixtures" / "aisi_blog.html"


class StubFetcher(Fetcher):
    def __init__(self, html: str) -> None:
        self._html = html

    async def fetch(self, url, *, render_mode, user_agent=None, encoding=None):
        return self._html


def _new_feed() -> Feed:
    return Feed(
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


def _setup(tmp_path) -> sqlite3.Connection:
    conn = db.connect(str(tmp_path / "t.sqlite3"))
    db.migrate(conn)
    return conn


@pytest.mark.asyncio
async def test_refresh_inserts_then_dedupes(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _new_feed())
    fetcher = StubFetcher(FIXTURE.read_text())

    await refresh_one(conn, fetcher, feed_id)
    items = db.list_items(conn, feed_id)
    assert len(items) == 2

    await refresh_one(conn, fetcher, feed_id)
    items_after = db.list_items(conn, feed_id)
    assert len(items_after) == 2
    assert {i.guid for i in items} == {i.guid for i in items_after}


@pytest.mark.asyncio
async def test_refresh_marks_error_on_no_match(tmp_path):
    conn = _setup(tmp_path)
    feed = _new_feed()
    feed.item_selector = ".does-not-exist"
    feed_id = db.insert_feed(conn, feed)
    fetcher = StubFetcher("<html></html>")

    await refresh_one(conn, fetcher, feed_id)
    saved = db.get_feed_by_id(conn, feed_id)
    assert saved is not None
    assert saved.last_status == "error"
    assert "no items matched" in (saved.last_error or "")
