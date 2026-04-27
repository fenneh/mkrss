from dataclasses import dataclass, field
from typing import Literal

ExtractionMode = Literal["css", "template"]
RenderMode = Literal["http", "browser"]


@dataclass
class FeedField:
    name: str
    selector: str
    attribute: str | None = None
    transform: str | None = None
    position: int = 0


@dataclass
class Feed:
    id: int
    slug: str
    source_url: str
    title: str
    description: str
    link: str
    extraction_mode: ExtractionMode
    render_mode: RenderMode
    item_selector: str | None
    global_pattern: str | None
    item_pattern: str | None
    reverse_order: bool
    title_template: str
    link_template: str
    description_template: str
    refresh_minutes: int
    user_agent: str | None
    encoding: str | None
    last_fetched_at: str | None
    last_status: str | None
    last_error: str | None
    last_item_count: int | None
    created_at: str
    updated_at: str
    fields: list[FeedField] = field(default_factory=list)


@dataclass
class Item:
    id: int
    feed_id: int
    guid: str
    title: str
    link: str
    description: str
    published_at: str | None
    raw_fields_json: str
    first_seen_at: str


@dataclass
class ExtractedItem:
    fields: dict[str, str]
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FieldSpec:
    name: str
    selector: str
    attribute: str | None
    transform: str | None


@dataclass(frozen=True)
class CssExtractionSpec:
    base_url: str
    item_selector: str
    fields: tuple[FieldSpec, ...]


@dataclass(frozen=True)
class TemplateExtractionSpec:
    global_pattern: str | None
    item_pattern: str
    reverse_order: bool
