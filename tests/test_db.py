import sqlite3

from mkrss import db
from mkrss.models import Feed, FeedField


def _setup(tmp_path) -> sqlite3.Connection:
    conn = db.connect(str(tmp_path / "t.sqlite3"))
    db.migrate(conn)
    return conn


def _feed(slug: str = "test-feed") -> Feed:
    return Feed(
        id=0,
        slug=slug,
        source_url="https://example.com/feed",
        title="Test Feed",
        description="",
        link="https://example.com",
        extraction_mode="css",
        render_mode="http",
        item_selector="article",
        global_pattern=None,
        item_pattern=None,
        reverse_order=False,
        title_template="{title}",
        link_template="{link}",
        description_template="{description}",
        refresh_minutes=30,
        user_agent=None,
        encoding=None,
        last_fetched_at=None,
        last_status=None,
        last_error=None,
        last_item_count=None,
        created_at="",
        updated_at="",
        fields=[],
    )


def _insert_item(conn, feed_id: int, guid: str, link: str | None = None) -> bool:
    return db.insert_item(
        conn,
        feed_id=feed_id,
        guid=guid,
        title=guid,
        link=link or f"https://example.com/{guid}",
        description="",
        published_at=None,
        raw_fields={},
    )


def test_insert_and_get_by_slug(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _feed())
    feed = db.get_feed_by_slug(conn, "test-feed")
    assert feed is not None
    assert feed.id == feed_id
    assert feed.title == "Test Feed"


def test_get_by_id_returns_none_for_missing(tmp_path):
    conn = _setup(tmp_path)
    assert db.get_feed_by_id(conn, 999) is None


def test_get_by_slug_returns_none_for_missing(tmp_path):
    conn = _setup(tmp_path)
    assert db.get_feed_by_slug(conn, "no-such-feed") is None


def test_update_feed_persists_title_and_fields(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _feed())
    feed = db.get_feed_by_id(conn, feed_id)
    assert feed is not None
    feed.title = "Renamed"
    feed.fields = [FeedField(name="title", selector="h1")]
    db.update_feed(conn, feed)
    reloaded = db.get_feed_by_id(conn, feed_id)
    assert reloaded is not None
    assert reloaded.title == "Renamed"
    assert len(reloaded.fields) == 1
    assert reloaded.fields[0].name == "title"


def test_delete_feed_cascades_to_items(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _feed())
    _insert_item(conn, feed_id, "g1")
    db.delete_feed(conn, feed_id)
    assert db.get_feed_by_id(conn, feed_id) is None
    assert db.list_items(conn, feed_id) == []


def test_list_feeds_returns_all(tmp_path):
    conn = _setup(tmp_path)
    db.insert_feed(conn, _feed("feed-a"))
    db.insert_feed(conn, _feed("feed-b"))
    feeds = db.list_feeds(conn)
    slugs = {f.slug for f in feeds}
    assert slugs == {"feed-a", "feed-b"}


def test_insert_item_deduplicates_by_guid(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _feed())
    assert _insert_item(conn, feed_id, "g1") is True
    assert _insert_item(conn, feed_id, "g1") is False
    assert len(db.list_items(conn, feed_id)) == 1


def test_prune_items_keeps_most_recent(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _feed())
    for i in range(5):
        _insert_item(conn, feed_id, f"g{i}")
    db.prune_items(conn, feed_id, keep=3)
    remaining = db.list_items(conn, feed_id, limit=100)
    assert len(remaining) == 3


def test_prune_items_noop_when_under_limit(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _feed())
    for i in range(2):
        _insert_item(conn, feed_id, f"g{i}")
    db.prune_items(conn, feed_id, keep=10)
    assert len(db.list_items(conn, feed_id, limit=100)) == 2


def test_update_feed_status(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _feed())
    db.update_feed_status(conn, feed_id, status="error", error="fetch failed", item_count=0)
    feed = db.get_feed_by_id(conn, feed_id)
    assert feed is not None
    assert feed.last_status == "error"
    assert feed.last_error == "fetch failed"
    assert feed.last_item_count == 0


def test_list_due_feed_ids_never_fetched(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _feed())
    assert feed_id in db.list_due_feed_ids(conn)


def test_list_due_feed_ids_just_fetched_not_due(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _feed())
    db.update_feed_status(conn, feed_id, status="ok", error=None, item_count=1)
    assert feed_id not in db.list_due_feed_ids(conn)


def test_list_due_feed_ids_stale_feed_is_due(tmp_path):
    conn = _setup(tmp_path)
    feed_id = db.insert_feed(conn, _feed())
    conn.execute("UPDATE feeds SET last_fetched_at='2000-01-01T00:00:00Z' WHERE id=?", (feed_id,))
    assert feed_id in db.list_due_feed_ids(conn)


def test_list_due_feed_ids_excludes_recent_feed(tmp_path):
    conn = _setup(tmp_path)
    feed_id_recent = db.insert_feed(conn, _feed("recent"))
    feed_id_stale = db.insert_feed(conn, _feed("stale"))
    db.update_feed_status(conn, feed_id_recent, status="ok", error=None, item_count=0)
    conn.execute("UPDATE feeds SET last_fetched_at='2000-01-01T00:00:00Z' WHERE id=?", (feed_id_stale,))
    due = db.list_due_feed_ids(conn)
    assert feed_id_stale in due
    assert feed_id_recent not in due
