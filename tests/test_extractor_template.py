from pathlib import Path

from mkrss.extractor_template import extract
from mkrss.models import TemplateExtractionSpec

FIXTURE = Path(__file__).parent / "fixtures" / "aisi_blog.html"

AISI_PATTERN = (
    '<div role="listitem" class="work-card-wrapper w-dyn-item">{*}'
    '<a href="/blog/{%}"{*}fs-list-field="title"{*}>{%}</h3>{*}'
    '<p fs-list-field="category"{*}>{%}</p>{*}'
    'fs-list-field="date"{*}>{%}</p>{*}'
    '<p fs-list-field="description"{*}>{%}</p>'
)


def test_aisi_template_pattern_extracts_two_items():
    html = FIXTURE.read_text()
    spec = TemplateExtractionSpec(global_pattern=None, item_pattern=AISI_PATTERN, reverse_order=False)
    items = extract(html, spec)
    assert len(items) == 2
    assert items[0].fields["1"] == "first-post"
    assert items[0].fields["2"] == "First Post"
    assert items[0].fields["3"] == "Research"
    assert items[0].fields["4"] == "2026-04-01"
    assert items[0].fields["5"] == "A first post about safety evals."


def test_reverse_order():
    html = FIXTURE.read_text()
    spec = TemplateExtractionSpec(global_pattern=None, item_pattern=AISI_PATTERN, reverse_order=True)
    items = extract(html, spec)
    assert items[0].fields["1"] == "second-post"
    assert items[1].fields["1"] == "first-post"


def test_global_pattern_constrains_scope():
    html = (
        "<header>X</header>"
        '<main><a href="/a">A</a><a href="/b">B</a></main>'
        '<footer><a href="/c">C</a></footer>'
    )
    spec = TemplateExtractionSpec(
        global_pattern="<main>{%}</main>",
        item_pattern='<a href="{%}">{%}</a>',
        reverse_order=False,
    )
    items = extract(html, spec)
    assert [i.fields["1"] for i in items] == ["/a", "/b"]


def test_no_match_returns_empty():
    spec = TemplateExtractionSpec(global_pattern=None, item_pattern="<x>{%}</x>", reverse_order=False)
    assert extract("<p>nope</p>", spec) == []


def test_p_aliases_match_numeric():
    html = FIXTURE.read_text()
    spec = TemplateExtractionSpec(global_pattern=None, item_pattern=AISI_PATTERN, reverse_order=False)
    items = extract(html, spec)
    assert items[0].fields["p1"] == items[0].fields["1"]
    assert items[0].fields["p5"] == items[0].fields["5"]
