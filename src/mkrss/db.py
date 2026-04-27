import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .models import Feed, FeedField, Item

MIGRATIONS: list[str] = [
    """
    CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
    """,
    """
    CREATE TABLE feeds (
      id                    INTEGER PRIMARY KEY AUTOINCREMENT,
      slug                  TEXT NOT NULL UNIQUE,
      source_url            TEXT NOT NULL,
      title                 TEXT NOT NULL,
      description           TEXT NOT NULL DEFAULT '',
      link                  TEXT NOT NULL,
      extraction_mode       TEXT NOT NULL CHECK (extraction_mode IN ('css','template')),
      render_mode           TEXT NOT NULL DEFAULT 'http'
                              CHECK (render_mode IN ('http','browser')),
      item_selector         TEXT,
      global_pattern        TEXT,
      item_pattern          TEXT,
      reverse_order         INTEGER NOT NULL DEFAULT 0,
      title_template        TEXT NOT NULL DEFAULT '{title}',
      link_template         TEXT NOT NULL DEFAULT '{link}',
      description_template  TEXT NOT NULL DEFAULT '{description}',
      refresh_minutes       INTEGER NOT NULL DEFAULT 30,
      user_agent            TEXT,
      encoding              TEXT,
      last_fetched_at       TEXT,
      last_status           TEXT,
      last_error            TEXT,
      last_item_count       INTEGER,
      created_at            TEXT NOT NULL,
      updated_at            TEXT NOT NULL
    );
    """,
    "CREATE INDEX idx_feeds_refresh ON feeds(last_fetched_at);",
    """
    CREATE TABLE feed_fields (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      feed_id     INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
      name        TEXT NOT NULL,
      selector    TEXT NOT NULL,
      attribute   TEXT,
      transform   TEXT,
      position    INTEGER NOT NULL DEFAULT 0,
      UNIQUE(feed_id, name)
    );
    """,
    """
    CREATE TABLE items (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      feed_id         INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
      guid            TEXT NOT NULL,
      title           TEXT NOT NULL,
      link            TEXT NOT NULL,
      description     TEXT NOT NULL DEFAULT '',
      published_at    TEXT,
      raw_fields_json TEXT NOT NULL,
      first_seen_at   TEXT NOT NULL,
      UNIQUE(feed_id, guid)
    );
    """,
    "CREATE INDEX idx_items_feed_seen ON items(feed_id, first_seen_at DESC);",
]


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
    has_table = cur.fetchone() is not None
    current = 0
    if has_table:
        row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        current = row["v"] or 0

    for i, sql in enumerate(MIGRATIONS, start=1):
        if i <= current:
            continue
        conn.executescript(sql)
        if i == 1:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (1,))
        else:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (i,))


def _row_to_feed(row: sqlite3.Row, fields: list[FeedField]) -> Feed:
    return Feed(
        id=row["id"],
        slug=row["slug"],
        source_url=row["source_url"],
        title=row["title"],
        description=row["description"],
        link=row["link"],
        extraction_mode=row["extraction_mode"],
        render_mode=row["render_mode"],
        item_selector=row["item_selector"],
        global_pattern=row["global_pattern"],
        item_pattern=row["item_pattern"],
        reverse_order=bool(row["reverse_order"]),
        title_template=row["title_template"],
        link_template=row["link_template"],
        description_template=row["description_template"],
        refresh_minutes=row["refresh_minutes"],
        user_agent=row["user_agent"],
        encoding=row["encoding"],
        last_fetched_at=row["last_fetched_at"],
        last_status=row["last_status"],
        last_error=row["last_error"],
        last_item_count=row["last_item_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        fields=fields,
    )


def _load_fields(conn: sqlite3.Connection, feed_id: int) -> list[FeedField]:
    rows = conn.execute(
        "SELECT name, selector, attribute, transform, position FROM feed_fields "
        "WHERE feed_id = ? ORDER BY position, id",
        (feed_id,),
    ).fetchall()
    return [
        FeedField(
            name=r["name"],
            selector=r["selector"],
            attribute=r["attribute"],
            transform=r["transform"],
            position=r["position"],
        )
        for r in rows
    ]


def get_feed_by_slug(conn: sqlite3.Connection, slug: str) -> Feed | None:
    row = conn.execute("SELECT * FROM feeds WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        return None
    return _row_to_feed(row, _load_fields(conn, row["id"]))


def get_feed_by_id(conn: sqlite3.Connection, feed_id: int) -> Feed | None:
    row = conn.execute("SELECT * FROM feeds WHERE id = ?", (feed_id,)).fetchone()
    if row is None:
        return None
    return _row_to_feed(row, _load_fields(conn, feed_id))


def list_feeds(conn: sqlite3.Connection) -> list[Feed]:
    rows = conn.execute("SELECT * FROM feeds ORDER BY created_at DESC").fetchall()
    return [_row_to_feed(r, _load_fields(conn, r["id"])) for r in rows]


def list_due_feed_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        """
        SELECT id FROM feeds
        WHERE last_fetched_at IS NULL
           OR (julianday('now') - julianday(last_fetched_at)) >= (refresh_minutes / 1440.0)
        """
    ).fetchall()
    return [r["id"] for r in rows]


def insert_feed(conn: sqlite3.Connection, feed: Feed) -> int:
    ts = now_iso()
    cur = conn.execute(
        """
        INSERT INTO feeds (
          slug, source_url, title, description, link,
          extraction_mode, render_mode,
          item_selector, global_pattern, item_pattern, reverse_order,
          title_template, link_template, description_template,
          refresh_minutes, user_agent, encoding,
          created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            feed.slug,
            feed.source_url,
            feed.title,
            feed.description,
            feed.link,
            feed.extraction_mode,
            feed.render_mode,
            feed.item_selector,
            feed.global_pattern,
            feed.item_pattern,
            int(feed.reverse_order),
            feed.title_template,
            feed.link_template,
            feed.description_template,
            feed.refresh_minutes,
            feed.user_agent,
            feed.encoding,
            ts,
            ts,
        ),
    )
    feed_id = cur.lastrowid
    assert feed_id is not None
    replace_fields(conn, feed_id, feed.fields)
    return feed_id


def update_feed(conn: sqlite3.Connection, feed: Feed) -> None:
    conn.execute(
        """
        UPDATE feeds SET
          source_url=?, title=?, description=?, link=?,
          extraction_mode=?, render_mode=?,
          item_selector=?, global_pattern=?, item_pattern=?, reverse_order=?,
          title_template=?, link_template=?, description_template=?,
          refresh_minutes=?, user_agent=?, encoding=?,
          updated_at=?
        WHERE id=?
        """,
        (
            feed.source_url,
            feed.title,
            feed.description,
            feed.link,
            feed.extraction_mode,
            feed.render_mode,
            feed.item_selector,
            feed.global_pattern,
            feed.item_pattern,
            int(feed.reverse_order),
            feed.title_template,
            feed.link_template,
            feed.description_template,
            feed.refresh_minutes,
            feed.user_agent,
            feed.encoding,
            now_iso(),
            feed.id,
        ),
    )
    replace_fields(conn, feed.id, feed.fields)


def replace_fields(conn: sqlite3.Connection, feed_id: int, fields: Iterable[FeedField]) -> None:
    conn.execute("DELETE FROM feed_fields WHERE feed_id = ?", (feed_id,))
    for i, f in enumerate(fields):
        conn.execute(
            """
            INSERT INTO feed_fields (feed_id, name, selector, attribute, transform, position)
            VALUES (?,?,?,?,?,?)
            """,
            (feed_id, f.name, f.selector, f.attribute, f.transform, i),
        )


def delete_feed(conn: sqlite3.Connection, feed_id: int) -> None:
    conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))


def update_feed_status(
    conn: sqlite3.Connection,
    feed_id: int,
    *,
    status: str,
    error: str | None,
    item_count: int | None,
) -> None:
    conn.execute(
        """
        UPDATE feeds SET
          last_status=?, last_error=?, last_item_count=?, last_fetched_at=?, updated_at=?
        WHERE id=?
        """,
        (status, error, item_count, now_iso(), now_iso(), feed_id),
    )


def insert_item(
    conn: sqlite3.Connection,
    *,
    feed_id: int,
    guid: str,
    title: str,
    link: str,
    description: str,
    published_at: str | None,
    raw_fields: dict[str, str],
) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO items
          (feed_id, guid, title, link, description, published_at, raw_fields_json, first_seen_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            feed_id,
            guid,
            title,
            link,
            description,
            published_at,
            json.dumps(raw_fields, ensure_ascii=False),
            now_iso(),
        ),
    )
    return cur.rowcount > 0


def prune_items(conn: sqlite3.Connection, feed_id: int, keep: int = 100) -> None:
    conn.execute(
        """
        DELETE FROM items
        WHERE feed_id = ?
          AND id NOT IN (
            SELECT id FROM items WHERE feed_id = ?
            ORDER BY first_seen_at DESC, id DESC LIMIT ?
          )
        """,
        (feed_id, feed_id, keep),
    )


def list_items(conn: sqlite3.Connection, feed_id: int, limit: int = 50) -> list[Item]:
    rows = conn.execute(
        """
        SELECT * FROM items WHERE feed_id = ?
        ORDER BY first_seen_at DESC, id DESC LIMIT ?
        """,
        (feed_id, limit),
    ).fetchall()
    return [
        Item(
            id=r["id"],
            feed_id=r["feed_id"],
            guid=r["guid"],
            title=r["title"],
            link=r["link"],
            description=r["description"],
            published_at=r["published_at"],
            raw_fields_json=r["raw_fields_json"],
            first_seen_at=r["first_seen_at"],
        )
        for r in rows
    ]
