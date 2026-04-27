from mkrss.models import Feed, Item
from mkrss.rss import build_feed_xml


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
