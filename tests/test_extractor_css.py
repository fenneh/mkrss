from pathlib import Path

from mkrss.extractor_css import extract
from mkrss.models import CssExtractionSpec, FieldSpec

FIXTURE = Path(__file__).parent / "fixtures" / "aisi_blog.html"


def _spec() -> CssExtractionSpec:
    return CssExtractionSpec(
        base_url="https://www.aisi.gov.uk/blog",
        item_selector="div.work-card-wrapper.w-dyn-item",
        fields=(
            FieldSpec(
                name="link",
                selector='a[href*="/blog/"]',
                attribute="href",
                transform="absolute_url",
            ),
            FieldSpec(name="title", selector='[fs-list-field="title"]', attribute=None, transform=None),
            FieldSpec(name="category", selector='[fs-list-field="category"]', attribute=None, transform=None),
            FieldSpec(
                name="date",
                selector='[fs-list-field="date"]',
                attribute=None,
                transform="parse_date",
            ),
            FieldSpec(
                name="description",
                selector='[fs-list-field="description"]',
                attribute=None,
                transform=None,
            ),
        ),
    )


def test_extracts_two_items():
    html = FIXTURE.read_text()
    items = extract(html, _spec())
    assert len(items) == 2


def test_link_resolved_absolute():
    html = FIXTURE.read_text()
    items = extract(html, _spec())
    assert items[0].fields["link"] == "https://www.aisi.gov.uk/blog/first-post"
    assert items[1].fields["link"] == "https://www.aisi.gov.uk/blog/second-post"


def test_text_fields():
    html = FIXTURE.read_text()
    items = extract(html, _spec())
    assert items[0].fields["title"] == "First Post"
    assert items[0].fields["category"] == "Research"
    assert items[0].fields["description"] == "A first post about safety evals."


def test_date_parsed_to_iso():
    html = FIXTURE.read_text()
    items = extract(html, _spec())
    assert items[0].fields["date"].startswith("2026-04-01")


def test_missing_selector_records_error():
    spec = CssExtractionSpec(
        base_url="https://example.com",
        item_selector="div.work-card-wrapper.w-dyn-item",
        fields=(FieldSpec(name="missing", selector=".does-not-exist", attribute=None, transform=None),),
    )
    items = extract(FIXTURE.read_text(), spec)
    assert items
    assert items[0].fields["missing"] == ""
    assert any("matched nothing" in e for e in items[0].errors)
