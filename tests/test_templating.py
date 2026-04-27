import pytest

from mkrss.templating import TemplateError, render


def test_named_placeholder_html_escaped():
    out = render("<p>{title}</p>", {"title": "<b>x</b>"})
    assert out == "<p>&lt;b&gt;x&lt;/b&gt;</p>"


def test_raw_suffix_skips_escape():
    out = render("<p>{description:raw}</p>", {"description": "<em>x</em>"})
    assert out == "<p><em>x</em></p>"


def test_positional_percent_alias():
    out = render("https://x.test/{%1}", {"p1": "abc", "1": "abc"})
    assert out == "https://x.test/abc"


def test_combined_template_from_aisi_example():
    fields = {
        "p1": "first-post",
        "p2": "First Post",
        "p3": "Research",
        "p4": "2026-04-01",
        "p5": "A safety post.",
        "1": "first-post",
        "2": "First Post",
        "3": "Research",
        "4": "2026-04-01",
        "5": "A safety post.",
    }
    template = "<p><strong>{%3}</strong> &mdash; {%4}</p><p>{%5}</p>"
    out = render(template, fields)
    assert out == "<p><strong>Research</strong> &mdash; 2026-04-01</p><p>A safety post.</p>"


def test_unknown_placeholder_raises():
    with pytest.raises(TemplateError):
        render("{nope}", {})


def test_unsupported_format_spec_raises():
    with pytest.raises(TemplateError):
        render("{title:weird}", {"title": "x"})
