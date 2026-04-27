"""Seed an example feed if the DB is empty.

Usage: uv run python scripts/seed.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mkrss import db, slugs
from mkrss.config import load
from mkrss.models import Feed, FeedField


def main() -> None:
    cfg = load()
    conn = db.connect(cfg.db_path)
    db.migrate(conn)

    if db.list_feeds(conn):
        print(f"DB at {cfg.db_path} already has feeds; nothing to seed.")
        return

    aisi = Feed(
        id=0,
        slug=slugs.generate("aisi-blog"),
        source_url="https://www.aisi.gov.uk/blog",
        title="AISI Blog",
        description="Posts from the UK AI Security Institute blog",
        link="https://www.aisi.gov.uk/blog",
        extraction_mode="css",
        render_mode="http",
        item_selector="div.work-card-wrapper.w-dyn-item",
        global_pattern=None,
        item_pattern=None,
        reverse_order=False,
        title_template="{title}",
        link_template="{link}",
        description_template=(
            "<p><strong>{category}</strong> &mdash; {date}</p><p>{description:raw}</p><hr>{body:raw}"
        ),
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
            FeedField(name="date", selector='[fs-list-field="date"]', transform="parse_date"),
            FeedField(name="description", selector='[fs-list-field="description"]'),
            FeedField(name="body", selector="article", source="post", transform="raw_html"),
        ],
    )
    feed_id = db.insert_feed(conn, aisi)
    saved = db.get_feed_by_id(conn, feed_id)
    assert saved is not None
    print(f"Seeded AISI Blog as /feeds/{saved.slug}.xml")


if __name__ == "__main__":
    main()
