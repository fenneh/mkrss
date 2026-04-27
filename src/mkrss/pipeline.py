"""Shared extraction + template-render pipeline used by both the
refresh worker and the editor's HTMX preview endpoint."""

from dataclasses import dataclass
from hashlib import sha256

from . import extractor_css, extractor_template
from .models import (
    CssExtractionSpec,
    ExtractedItem,
    Feed,
    FieldSpec,
    TemplateExtractionSpec,
)
from .templating import TemplateError, render


@dataclass
class RenderedItem:
    title: str
    link: str
    description: str
    raw_fields: dict[str, str]
    published_at: str | None
    errors: list[str]

    @property
    def guid(self) -> str:
        return sha256(self.link.encode()).hexdigest()


def extract(feed: Feed, html: str) -> list[ExtractedItem]:
    if feed.extraction_mode == "css":
        if not feed.item_selector:
            return []
        spec = CssExtractionSpec(
            base_url=feed.source_url,
            item_selector=feed.item_selector,
            fields=tuple(
                FieldSpec(name=f.name, selector=f.selector, attribute=f.attribute, transform=f.transform)
                for f in feed.fields
            ),
        )
        return extractor_css.extract(html, spec)
    if not feed.item_pattern:
        return []
    return extractor_template.extract(
        html,
        TemplateExtractionSpec(
            global_pattern=feed.global_pattern,
            item_pattern=feed.item_pattern,
            reverse_order=feed.reverse_order,
        ),
    )


def render_items(feed: Feed, extracted: list[ExtractedItem]) -> list[RenderedItem]:
    out: list[RenderedItem] = []
    for ex in extracted:
        errors = list(ex.errors)
        try:
            title = render(feed.title_template, ex.fields).strip()
            link = render(feed.link_template, ex.fields).strip()
            description = render(feed.description_template, ex.fields).strip()
        except TemplateError as e:
            errors.append(str(e))
            title, link, description = "", "", ""
        published_at = ex.fields.get("date") or ex.fields.get("published") or None
        out.append(
            RenderedItem(
                title=title or link,
                link=link,
                description=description,
                raw_fields=ex.fields,
                published_at=published_at,
                errors=errors,
            )
        )
    return out
