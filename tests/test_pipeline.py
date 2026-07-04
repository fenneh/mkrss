from hashlib import sha256

from mkrss.models import ExtractedItem, Feed, FeedField
from mkrss.pipeline import RenderedItem, extract, post_fields, render_items


def _feed(**overrides) -> Feed:
    base = Feed(
        id=1,
        slug="test",
        source_url="https://example.com",
        title="Test",
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
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _item(**extra) -> ExtractedItem:
    return ExtractedItem(fields={"title": "T", "link": "https://example.com/1", "description": "D", **extra})


# --- render_items ---

def test_render_items_basic():
    items = render_items(_feed(), [_item()])
    assert len(items) == 1
    r = items[0]
    assert r.title == "T"
    assert r.link == "https://example.com/1"
    assert r.description == "D"
    assert r.errors == []


def test_render_items_title_falls_back_to_link():
    ex = ExtractedItem(fields={"title": "", "link": "https://example.com/a", "description": ""})
    items = render_items(_feed(), [ex])
    assert items[0].title == "https://example.com/a"


def test_render_items_date_field_sets_published_at():
    items = render_items(_feed(), [_item(date="2026-01-01T00:00:00Z")])
    assert items[0].published_at == "2026-01-01T00:00:00Z"


def test_render_items_published_field_as_fallback():
    items = render_items(_feed(), [_item(published="2025-12-01")])
    assert items[0].published_at == "2025-12-01"


def test_render_items_date_preferred_over_published():
    items = render_items(_feed(), [_item(date="2026-01-01", published="2025-01-01")])
    assert items[0].published_at == "2026-01-01"


def test_render_items_no_date_returns_none():
    ex = ExtractedItem(fields={"title": "T", "link": "https://example.com", "description": ""})
    items = render_items(_feed(), [ex])
    assert items[0].published_at is None


def test_render_items_template_error_blanks_fields_and_records_error():
    feed = _feed(title_template="{notpresent}")
    ex = ExtractedItem(fields={"link": "https://example.com", "description": ""})
    items = render_items(feed, [ex])
    r = items[0]
    assert r.title == ""
    assert r.link == ""
    assert len(r.errors) == 1
    assert "notpresent" in r.errors[0]


def test_render_items_propagates_extractor_errors():
    ex = _item()
    ex.errors.append("selector missed")
    items = render_items(_feed(), [ex])
    assert "selector missed" in items[0].errors


def test_render_items_multiple():
    ex1 = _item(title="A", link="https://example.com/a")
    ex2 = _item(title="B", link="https://example.com/b")
    items = render_items(_feed(), [ex1, ex2])
    assert [r.title for r in items] == ["A", "B"]


# --- RenderedItem.guid ---

def test_rendered_item_guid_is_sha256_of_link():
    link = "https://example.com/post/1"
    r = RenderedItem(title="T", link=link, description="", raw_fields={}, published_at=None, errors=[])
    assert r.guid == sha256(link.encode()).hexdigest()


# --- post_fields ---

def test_post_fields_returns_post_source_only():
    feed = _feed(
        extraction_mode="css",
        fields=[
            FeedField(name="title", selector="h1", source="item"),
            FeedField(name="body", selector="article", source="post"),
        ],
    )
    result = post_fields(feed)
    assert len(result) == 1
    assert result[0].name == "body"


def test_post_fields_empty_for_template_mode():
    feed = _feed(
        extraction_mode="template",
        fields=[FeedField(name="body", selector="article", source="post")],
    )
    assert post_fields(feed) == ()


def test_post_fields_empty_when_none_are_post_source():
    feed = _feed(fields=[FeedField(name="title", selector="h1", source="item")])
    assert post_fields(feed) == ()


# --- extract dispatch ---

def test_extract_css_no_item_selector_returns_empty():
    feed = _feed(extraction_mode="css", item_selector=None)
    assert extract(feed, "<ul><li>x</li></ul>") == []


def test_extract_template_no_item_pattern_returns_empty():
    feed = _feed(extraction_mode="template", item_pattern=None)
    assert extract(feed, "<p>hello</p>") == []


def test_extract_css_dispatches_to_css_extractor():
    feed = _feed(
        extraction_mode="css",
        item_selector="li",
        fields=[FeedField(name="title", selector="span")],
    )
    items = extract(feed, "<ul><li><span>One</span></li><li><span>Two</span></li></ul>")
    assert len(items) == 2
    assert items[0].fields["title"] == "One"
    assert items[1].fields["title"] == "Two"


def test_extract_template_dispatches_to_template_extractor():
    feed = _feed(extraction_mode="template", item_pattern="<li>{%}</li>")
    items = extract(feed, "<ul><li>Alpha</li><li>Beta</li></ul>")
    assert len(items) == 2
    assert items[0].fields["1"] == "Alpha"
    assert items[1].fields["1"] == "Beta"
