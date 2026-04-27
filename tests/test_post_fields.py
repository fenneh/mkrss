from pathlib import Path

import pytest

from mkrss import db
from mkrss.fetch import Fetcher
from mkrss.models import Feed, FeedField
from mkrss.refresh import refresh_one

LISTING = Path(__file__).parent / "fixtures" / "aisi_blog.html"
POST = Path(__file__).parent / "fixtures" / "aisi_post.html"


class StubFetcher(Fetcher):
    def __init__(self, listing_html: str, post_html: str) -> None:
        self.listing = listing_html
        self.post = post_html
        self.fetches: list[str] = []

    async def fetch(self, url, *, render_mode, user_agent=None, encoding=None):
        self.fetches.append(url)
        if url.endswith("/blog"):
            return self.listing
        return self.post


def _feed_with_post_body() -> Feed:
    return Feed(
        id=0,
        slug="aisi-post-test",
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
        description_template="<div>{description}</div><div>{body:raw}</div>",
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
            FeedField(
                name="link",
                selector='a[href*="/blog/"]',
                attribute="href",
                transform="absolute_url",
            ),
            FeedField(name="title", selector='[fs-list-field="title"]'),
            FeedField(name="description", selector='[fs-list-field="description"]'),
            FeedField(name="body", selector="article", source="post", transform="raw_html"),
        ],
    )


@pytest.mark.asyncio
async def test_post_fields_followed_and_inserted(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite3"))
    db.migrate(conn)
    feed_id = db.insert_feed(conn, _feed_with_post_body())
    fetcher = StubFetcher(LISTING.read_text(), POST.read_text())

    await refresh_one(conn, fetcher, feed_id)

    fetched = [u for u in fetcher.fetches]
    assert any(u.endswith("/blog") for u in fetched), "listing not fetched"
    assert any("/blog/first-post" in u for u in fetched), "post page not fetched"

    items = db.list_items(conn, feed_id)
    assert items
    assert any("Paragraph one of the body" in i.description for i in items)


@pytest.mark.asyncio
async def test_post_fetch_skipped_for_existing_items(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite3"))
    db.migrate(conn)
    feed_id = db.insert_feed(conn, _feed_with_post_body())
    fetcher = StubFetcher(LISTING.read_text(), POST.read_text())

    await refresh_one(conn, fetcher, feed_id)
    listing_only = sum(1 for u in fetcher.fetches if u.endswith("/blog"))
    posts_first = sum(1 for u in fetcher.fetches if "/blog/" in u and not u.endswith("/blog"))

    fetcher.fetches.clear()
    await refresh_one(conn, fetcher, feed_id)
    listing_only_2 = sum(1 for u in fetcher.fetches if u.endswith("/blog"))
    posts_second = sum(1 for u in fetcher.fetches if "/blog/" in u and not u.endswith("/blog"))

    assert listing_only == 1 and listing_only_2 == 1
    assert posts_first == 2  # both items are new on first run
    assert posts_second == 0  # already deduped on second run
