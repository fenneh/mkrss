import logging
import sqlite3

from . import db
from .fetch import Fetcher
from .pipeline import extract, render_items

logger = logging.getLogger(__name__)


async def refresh_one(conn: sqlite3.Connection, fetcher: Fetcher, feed_id: int) -> None:
    feed = db.get_feed_by_id(conn, feed_id)
    if feed is None:
        return

    try:
        html = await fetcher.fetch(
            feed.source_url,
            render_mode=feed.render_mode,
            user_agent=feed.user_agent,
            encoding=feed.encoding,
        )
    except Exception as e:
        logger.warning("fetch failed for feed %s: %s", feed.slug, e)
        db.update_feed_status(conn, feed_id, status="error", error=f"fetch: {e}", item_count=None)
        return

    try:
        extracted = extract(feed, html)
    except Exception as e:
        logger.warning("extract failed for feed %s: %s", feed.slug, e)
        db.update_feed_status(conn, feed_id, status="error", error=f"extract: {e}", item_count=None)
        return

    if not extracted:
        db.update_feed_status(
            conn,
            feed_id,
            status="error",
            error="no items matched (selector/pattern wrong, or page may need browser mode)",
            item_count=0,
        )
        return

    rendered = render_items(feed, extracted)
    inserted = 0
    skipped = 0
    last_errors: list[str] = []
    for r in rendered:
        if not r.link:
            skipped += 1
            if r.errors:
                last_errors.extend(r.errors[:1])
            continue
        ok = db.insert_item(
            conn,
            feed_id=feed_id,
            guid=r.guid,
            title=r.title,
            link=r.link,
            description=r.description,
            published_at=r.published_at,
            raw_fields=r.raw_fields,
        )
        if ok:
            inserted += 1

    db.prune_items(conn, feed_id, keep=100)

    error: str | None = None
    if skipped:
        error = f"{skipped} items skipped (no link); first issue: {last_errors[0] if last_errors else 'n/a'}"
    db.update_feed_status(
        conn,
        feed_id,
        status="ok" if not error else "error",
        error=error,
        item_count=len(rendered),
    )
    logger.info(
        "refreshed feed %s: extracted=%d inserted=%d skipped=%d", feed.slug, len(rendered), inserted, skipped
    )


async def tick(conn: sqlite3.Connection, fetcher: Fetcher) -> None:
    due = db.list_due_feed_ids(conn)
    for feed_id in due:
        try:
            await refresh_one(conn, fetcher, feed_id)
        except Exception:
            logger.exception("unhandled error in refresh tick for feed %s", feed_id)
