from collections.abc import Iterable
from urllib.parse import urljoin

from dateutil import parser as date_parser
from selectolax.parser import HTMLParser, Node

from .models import CssExtractionSpec, ExtractedItem, FieldSpec


def _capture(node: Node, field: FieldSpec) -> tuple[str, str | None]:
    target = node.css_first(field.selector)
    if target is None:
        return "", f"selector '{field.selector}' matched nothing for field '{field.name}'"
    if field.attribute:
        return target.attributes.get(field.attribute) or "", None
    if field.transform == "raw_html":
        inner = "".join(child.html or "" for child in target.iter(include_text=True))
        return inner.strip(), None
    return target.text(deep=True, separator=" ", strip=True), None


def _apply_transform(value: str, transform: str | None, base_url: str) -> tuple[str, str | None]:
    if not transform or not value:
        return value, None
    if transform == "absolute_url":
        return urljoin(base_url, value), None
    if transform == "parse_date":
        try:
            return date_parser.parse(value).isoformat(), None
        except (ValueError, OverflowError) as e:
            return value, f"parse_date failed: {e}"
    if transform == "strip_html":
        return HTMLParser(value).text(deep=True, separator=" ", strip=True), None
    if transform == "raw_html":
        return value, None
    return value, f"unknown transform '{transform}'"


def _extract_fields(
    node: Node, fields: Iterable[FieldSpec], base_url: str
) -> tuple[dict[str, str], list[str]]:
    out: dict[str, str] = {}
    errors: list[str] = []
    for field in fields:
        value, err = _capture(node, field)
        if err:
            errors.append(err)
        value, terr = _apply_transform(value, field.transform, base_url)
        if terr:
            errors.append(terr)
        out[field.name] = value
    return out, errors


def extract(html: str, spec: CssExtractionSpec) -> list[ExtractedItem]:
    """Extract items from a listing page using item-source fields only."""
    tree = HTMLParser(html)
    item_fields = tuple(f for f in spec.fields if f.source == "item")
    items: list[ExtractedItem] = []
    for node in tree.css(spec.item_selector):
        fields, errors = _extract_fields(node, item_fields, spec.base_url)
        items.append(ExtractedItem(fields=fields, errors=errors))
    return items


def extract_post(html: str, fields: Iterable[FieldSpec], base_url: str) -> tuple[dict[str, str], list[str]]:
    """Extract additional fields from a single followed post page."""
    tree = HTMLParser(html)
    root = tree.body or tree.root
    if root is None:
        return {}, ["could not parse post page"]
    return _extract_fields(root, fields, base_url)
