from datetime import UTC, datetime

from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator

from .models import Feed, Item


def _to_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        dt = date_parser.parse(value)
    except (ValueError, OverflowError):
        return datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def feed_self_url(base_url: str, slug: str) -> str:
    return f"{base_url.rstrip('/')}/feeds/{slug}.xml"


def build_feed_xml(feed: Feed, items: list[Item], *, base_url: str) -> bytes:
    fg = FeedGenerator()
    self_url = feed_self_url(base_url, feed.slug)
    fg.id(self_url)
    fg.title(feed.title)
    fg.link(href=self_url, rel="self")
    fg.link(href=feed.link, rel="alternate")
    fg.description(feed.description or feed.title)
    fg.language("en")
    fg.generator("mkrss")

    for item in items:
        fe = fg.add_entry()
        fe.id(item.guid)
        fe.title(item.title or item.link)
        fe.link(href=item.link)
        if item.description:
            fe.description(item.description)
        fe.guid(item.guid, permalink=False)
        fe.pubDate(_to_datetime(item.published_at or item.first_seen_at))

    return fg.rss_str(pretty=True)
