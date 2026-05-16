from datetime import UTC, datetime, timedelta

from mkrss.models import Feed, Item
from mkrss.rss import _to_datetime, build_feed_xml, feed_self_url


def _feed() -> Feed:
    return Feed(
        id=1,
        slug="aisi-blog-3f9c2a1b",
        source_url="https://www.aisi.gov.uk/blog",
        title="AISI Blog",
        description="Posts from AISI",
        link="https://www.aisi.gov.uk/blog",
        extraction_mode="css",
        render_mode="http",
        item_selector="div.work-card-wrapper",
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
        created_at="2026-04-27T00:00:00Z",
        updated_at="2026-04-27T00:00:00Z",
        fields=[],
    )


def _item(suffix: str) -> Item:
    return Item(
        id=int(suffix[-1]) if suffix[-1].isdigit() else 1,
        feed_id=1,
        guid=f"guid-{suffix}",
        title=f"Title {suffix}",
        link=f"https://www.aisi.gov.uk/blog/{suffix}",
        description=f"<p>Body {suffix}</p>",
        published_at="2026-04-25T10:00:00Z",
        raw_fields_json="{}",
        first_seen_at="2026-04-25T10:00:00Z",
    )


def test_builds_well_formed_rss():
    xml = build_feed_xml(_feed(), [_item("a"), _item("b")], base_url="https://mkrss.local")
    text = xml.decode()
    assert "<rss" in text
    assert "<channel>" in text
    assert "<title>AISI Blog</title>" in text
    assert "https://mkrss.local/feeds/aisi-blog-3f9c2a1b.xml" in text
    assert "Title a" in text
    assert "Title b" in text
    assert "https://www.aisi.gov.uk/blog/a" in text


def test_self_link_uses_base_url():
    xml = build_feed_xml(_feed(), [], base_url="http://localhost:8000")
    assert b"http://localhost:8000/feeds/aisi-blog-3f9c2a1b.xml" in xml


def test_feed_self_url_strips_trailing_slash():
    assert feed_self_url("https://example.com/", "my-feed") == "https://example.com/feeds/my-feed.xml"


def test_to_datetime_none_returns_utc_now():
    before = datetime.now(UTC)
    result = _to_datetime(None)
    after = datetime.now(UTC)
    assert before <= result <= after
    assert result.tzinfo is not None


def test_to_datetime_empty_returns_utc_now():
    before = datetime.now(UTC)
    result = _to_datetime("")
    after = datetime.now(UTC)
    assert before <= result <= after


def test_to_datetime_iso_with_tz_preserved():
    result = _to_datetime("2026-04-01T10:00:00+00:00")
    assert result == datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)


def test_to_datetime_naive_gets_utc():
    result = _to_datetime("2026-04-01T10:00:00")
    assert result.tzinfo is UTC
    assert result.year == 2026 and result.month == 4 and result.day == 1


def test_to_datetime_non_utc_offset_preserved():
    result = _to_datetime("2026-04-01T12:00:00+02:00")
    assert result.utcoffset() == timedelta(hours=2)


def test_to_datetime_invalid_string_returns_utc_now():
    before = datetime.now(UTC)
    result = _to_datetime("not-a-date")
    after = datetime.now(UTC)
    assert before <= result <= after
    assert result.tzinfo is not None
