import re

from .models import ExtractedItem, TemplateExtractionSpec

_CAPTURE = "{%}"
_WILDCARD = "{*}"


def _compile(pattern: str, *, anchor_full_match: bool) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith(_CAPTURE, i):
            out.append("(.*?)")
            i += len(_CAPTURE)
        elif pattern.startswith(_WILDCARD, i):
            out.append(".*?")
            i += len(_WILDCARD)
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    body = "".join(out)
    if anchor_full_match:
        body = f"(?s){body}"
    return re.compile(body, re.DOTALL)


def extract(html: str, spec: TemplateExtractionSpec) -> list[ExtractedItem]:
    text = html
    if spec.global_pattern:
        gre = _compile(spec.global_pattern, anchor_full_match=False)
        m = gre.search(text)
        if m is None:
            return []
        text = m.group(0)

    item_re = _compile(spec.item_pattern, anchor_full_match=False)
    items: list[ExtractedItem] = []
    for match in item_re.finditer(text):
        groups = match.groups()
        fields: dict[str, str] = {}
        for idx, value in enumerate(groups, start=1):
            v = value or ""
            fields[f"p{idx}"] = v
            fields[str(idx)] = v
        items.append(ExtractedItem(fields=fields))

    if spec.reverse_order:
        items.reverse()
    return items
