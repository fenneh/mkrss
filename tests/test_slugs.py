import pytest

from mkrss.slugs import slugify


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
