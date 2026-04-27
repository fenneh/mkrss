import logging
import sqlite3
from hashlib import sha256

from . import db
from .fetch import Fetcher
from .pipeline import enrich_with_post, extract, post_fields, render_items
from .templating import TemplateError, render

logger = logging.getLogger(__name__)

POST_FETCH_LIMIT_PER_REFRESH = 12


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

    has_post_fields = bool(post_fields(feed))
    existing_guids = {
        r["guid"] for r in conn.execute("SELECT guid FROM items WHERE feed_id = ?", (feed_id,)).fetchall()
    }

    inserted = 0
    skipped = 0
    post_fetched = 0
    last_errors: list[str] = []

    for ex in extracted:
        try:
            link = render(feed.link_template, ex.fields).strip()
        except TemplateError as e:
            skipped += 1
            last_errors.append(f"link template: {e}")
            continue
        if not link:
            skipped += 1
            continue

        guid = sha256(link.encode()).hexdigest()
        if guid in existing_guids:
            continue

        if has_post_fields and post_fetched < POST_FETCH_LIMIT_PER_REFRESH:
            await enrich_with_post(feed, ex, link, fetcher)
            post_fetched += 1
        elif has_post_fields:
            for f in post_fields(feed):
                ex.fields.setdefault(f.name, "")

        rendered = render_items(feed, [ex])[0]
        if rendered.errors:
            last_errors.extend(rendered.errors[:1])
        ok = db.insert_item(
            conn,
            feed_id=feed_id,
            guid=guid,
            title=rendered.title,
            link=link,
            description=rendered.description,
            published_at=rendered.published_at,
            raw_fields=rendered.raw_fields,
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
        item_count=len(extracted),
    )
    logger.info(
        "refreshed feed %s: extracted=%d inserted=%d post_fetched=%d skipped=%d",
        feed.slug,
        len(extracted),
        inserted,
        post_fetched,
        skipped,
    )


async def tick(conn: sqlite3.Connection, fetcher: Fetcher) -> None:
    due = db.list_due_feed_ids(conn)
    for feed_id in due:
        try:
            await refresh_one(conn, fetcher, feed_id)
        except Exception:
            logger.exception("unhandled error in refresh tick for feed %s", feed_id)
