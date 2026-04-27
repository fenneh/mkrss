from urllib.parse import urljoin

from dateutil import parser as date_parser
from selectolax.parser import HTMLParser, Node

from .models import CssExtractionSpec, ExtractedItem, FieldSpec


def _capture(node: Node, field: FieldSpec) -> tuple[str, str | None]:
    target = node.css_first(field.selector)
    if target is None:
        return "", f"selector '{field.selector}' matched nothing for field '{field.name}'"
    if field.attribute:
        value = target.attributes.get(field.attribute) or ""
    else:
        value = target.text(deep=True, separator=" ", strip=True)
    return value, None


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
    return value, f"unknown transform '{transform}'"


def extract(html: str, spec: CssExtractionSpec) -> list[ExtractedItem]:
    tree = HTMLParser(html)
    items: list[ExtractedItem] = []
    for node in tree.css(spec.item_selector):
        fields: dict[str, str] = {}
        errors: list[str] = []
        for field in spec.fields:
            value, err = _capture(node, field)
            if err:
                errors.append(err)
            value, terr = _apply_transform(value, field.transform, spec.base_url)
            if terr:
                errors.append(terr)
            fields[field.name] = value
        items.append(ExtractedItem(fields=fields, errors=errors))
    return items
