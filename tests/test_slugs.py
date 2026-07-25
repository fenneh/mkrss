import re

import pytest

from mkrss.slugs import ADJECTIVES, NOUNS, generate, slugify


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hello World", "hello-world"),
        ("RSS Feed 2025", "rss-feed-2025"),
        ("my-feed", "my-feed"),
        ("foo   bar", "foo-bar"),
        ("foo!bar@baz", "foo-bar-baz"),
        ("!!foo!!", "foo"),
        ("  leading and trailing  ", "leading-and-trailing"),
        ("café", "caf"),
        ("", "feed"),
        ("   ", "feed"),
        ("---", "feed"),
        ("123", "123"),
    ],
)
def test_slugify(text, expected):
    assert slugify(text) == expected


_HEX8 = re.compile(r"[0-9a-f]{8}$")


def test_generate_with_seed_uses_slugified_base():
    result = generate("Hello World")
    assert result.startswith("hello-world-")
    assert _HEX8.search(result)


def test_generate_without_seed_uses_adjective_noun():
    result = generate()
    parts = result.rsplit("-", 1)
    assert len(parts) == 2
    prefix, suffix = parts
    assert _HEX8.match(suffix)
    adj, noun = prefix.split("-", 1)
    assert adj in ADJECTIVES
    assert noun in NOUNS


def test_generate_with_empty_string_uses_random_slug():
    # empty string is falsy, so generate falls through to the adjective-noun branch
    result = generate("")
    parts = result.rsplit("-", 1)
    assert _HEX8.match(parts[1])


def test_generate_returns_unique_slugs():
    slugs = {generate() for _ in range(10)}
    assert len(slugs) == 10
