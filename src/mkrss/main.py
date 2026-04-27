import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth, db, slugs
from .config import Config, load
from .fetch import Fetcher
from .models import Feed, FeedField
from .pipeline import extract as run_extract
from .pipeline import render_items
from .refresh import refresh_one, tick
from .rss import build_feed_xml, feed_self_url

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg: Config = load()
    if not cfg.editor_password:
        logger.warning("EDITOR_PASSWORD is not set — editor routes will return 404")
    if cfg.session_secret == "dev-secret-change-me":
        logger.warning("SESSION_SECRET is using the dev default — set it in production")

    conn = db.connect(cfg.db_path)
    db.migrate(conn)

    fetcher = Fetcher()
    await fetcher.start()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(tick, IntervalTrigger(minutes=1), args=[conn, fetcher], id="tick")
    scheduler.start()

    app.state.cfg = cfg
    app.state.conn = conn
    app.state.fetcher = fetcher
    app.state.scheduler = scheduler

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await fetcher.stop()
        conn.close()


app = FastAPI(lifespan=lifespan, title="mkrss")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def _cfg(request: Request) -> Config:
    return request.app.state.cfg


def _conn(request: Request) -> sqlite3.Connection:
    return request.app.state.conn


def _fetcher(request: Request) -> Fetcher:
    return request.app.state.fetcher


def _editor_or_redirect(request: Request) -> RedirectResponse | None:
    cfg = _cfg(request)
    if not cfg.editor_password:
        return RedirectResponse("/disabled", status_code=303)
    if not auth.is_authenticated(cfg, request):
        return RedirectResponse("/login", status_code=303)
    return None


def _render(name: str, request: Request, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {"request": request, **ctx})


def _form_to_feed(form, *, existing: Feed | None = None) -> Feed:
    extraction_mode = form.get("extraction_mode") or "css"
    if extraction_mode not in ("css", "template"):
        extraction_mode = "css"
    render_mode = form.get("render_mode") or "http"
    if render_mode not in ("http", "browser"):
        render_mode = "http"

    fields: list[FeedField] = []
    if extraction_mode == "css":
        names = form.getlist("field_name")
        selectors = form.getlist("field_selector")
        attributes = form.getlist("field_attribute")
        transforms = form.getlist("field_transform")
        for i, name in enumerate(names):
            name = (name or "").strip()
            sel = (selectors[i] if i < len(selectors) else "").strip()
            if not name or not sel:
                continue
            attr = (attributes[i] if i < len(attributes) else "").strip() or None
            trans = (transforms[i] if i < len(transforms) else "").strip() or None
            fields.append(FeedField(name=name, selector=sel, attribute=attr, transform=trans, position=i))

    return Feed(
        id=existing.id if existing else 0,
        slug=existing.slug if existing else slugs.generate(form.get("slug_seed") or form.get("title")),
        source_url=(form.get("source_url") or "").strip(),
        title=(form.get("title") or "").strip() or "Untitled feed",
        description=(form.get("description") or "").strip(),
        link=(form.get("link") or form.get("source_url") or "").strip(),
        extraction_mode=extraction_mode,
        render_mode=render_mode,
        item_selector=(form.get("item_selector") or "").strip() or None,
        global_pattern=(form.get("global_pattern") or "").strip() or None,
        item_pattern=(form.get("item_pattern") or "").strip() or None,
        reverse_order=bool(form.get("reverse_order")),
        title_template=(form.get("title_template") or "{title}").strip() or "{title}",
        link_template=(form.get("link_template") or "{link}").strip() or "{link}",
        description_template=(form.get("description_template") or "{description}").strip() or "{description}",
        refresh_minutes=max(1, int(form.get("refresh_minutes") or 30)),
        user_agent=(form.get("user_agent") or "").strip() or None,
        encoding=(form.get("encoding") or "").strip() or None,
        last_fetched_at=existing.last_fetched_at if existing else None,
        last_status=existing.last_status if existing else None,
        last_error=existing.last_error if existing else None,
        last_item_count=existing.last_item_count if existing else None,
        created_at=existing.created_at if existing else "",
        updated_at="",
        fields=fields,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/feeds/{slug}.xml")
def public_feed(slug: str, request: Request) -> Response:
    cfg = _cfg(request)
    conn = _conn(request)
    feed = db.get_feed_by_slug(conn, slug)
    if feed is None:
        return Response(status_code=404)
    items = db.list_items(conn, feed.id, limit=50)
    xml = build_feed_xml(feed, items, base_url=cfg.base_url)
    return Response(
        content=xml,
        media_type="application/rss+xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/disabled", response_class=HTMLResponse)
def disabled(request: Request) -> HTMLResponse:
    return _render("disabled.html", request)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    cfg = _cfg(request)
    if not cfg.editor_password:
        return RedirectResponse("/disabled", status_code=303)
    return _render("login.html", request, error=None)


@app.post("/login")
def login_submit(request: Request, password: str = Form(...)) -> Response:
    cfg = _cfg(request)
    if not cfg.editor_password:
        return RedirectResponse("/disabled", status_code=303)
    if not auth.verify_password(cfg, password):
        return templates.TemplateResponse(
            request, "login.html", {"request": request, "error": "Wrong password"}, status_code=401
        )
    response = RedirectResponse("/", status_code=303)
    auth.issue_session(cfg, response)
    return response


@app.post("/logout")
def logout(request: Request) -> Response:
    response = RedirectResponse("/login", status_code=303)
    auth.clear_session(_cfg(request), response)
    return response


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    redirect = _editor_or_redirect(request)
    if redirect:
        return redirect
    feeds = db.list_feeds(_conn(request))
    return _render("index.html", request, feeds=feeds, base_url=_cfg(request).base_url)


@app.get("/feeds/new", response_class=HTMLResponse)
def feed_new(request: Request) -> Response:
    redirect = _editor_or_redirect(request)
    if redirect:
        return redirect
    placeholder = Feed(
        id=0,
        slug="",
        source_url="",
        title="",
        description="",
        link="",
        extraction_mode="css",
        render_mode="http",
        item_selector=None,
        global_pattern=None,
        item_pattern=None,
        reverse_order=False,
        title_template="{title}",
        link_template="{link}",
        description_template="{description}",
        refresh_minutes=30,
        user_agent=None,
        encoding=None,
        last_fetched_at=None,
        last_status=None,
        last_error=None,
        last_item_count=None,
        created_at="",
        updated_at="",
        fields=[],
    )
    return _render("feed_edit.html", request, feed=placeholder, mode="new", base_url=_cfg(request).base_url)


@app.post("/feeds")
async def feed_create(request: Request) -> Response:
    redirect = _editor_or_redirect(request)
    if redirect:
        return redirect
    form = await request.form()
    feed = _form_to_feed(form, existing=None)
    conn = _conn(request)
    feed_id = db.insert_feed(conn, feed)
    try:
        await refresh_one(conn, _fetcher(request), feed_id)
    except Exception:
        logger.exception("initial refresh failed for new feed")
    saved = db.get_feed_by_id(conn, feed_id)
    assert saved is not None
    return RedirectResponse(f"/feeds/{saved.slug}/edit", status_code=303)


@app.get("/feeds/{slug}/edit", response_class=HTMLResponse)
def feed_edit_form(slug: str, request: Request) -> Response:
    redirect = _editor_or_redirect(request)
    if redirect:
        return redirect
    feed = db.get_feed_by_slug(_conn(request), slug)
    if feed is None:
        return Response(status_code=404)
    return _render("feed_edit.html", request, feed=feed, mode="edit", base_url=_cfg(request).base_url)


@app.post("/feeds/{slug}")
async def feed_save(slug: str, request: Request) -> Response:
    redirect = _editor_or_redirect(request)
    if redirect:
        return redirect
    conn = _conn(request)
    existing = db.get_feed_by_slug(conn, slug)
    if existing is None:
        return Response(status_code=404)
    form = await request.form()
    updated = _form_to_feed(form, existing=existing)
    db.update_feed(conn, updated)
    return RedirectResponse(f"/feeds/{slug}/edit", status_code=303)


@app.post("/feeds/{slug}/test", response_class=HTMLResponse)
async def feed_test(slug: str, request: Request) -> Response:
    redirect = _editor_or_redirect(request)
    if redirect:
        return redirect
    conn = _conn(request)
    existing = db.get_feed_by_slug(conn, slug)
    if existing is None:
        return Response(status_code=404)
    form = await request.form()
    candidate = _form_to_feed(form, existing=existing)
    fetcher = _fetcher(request)
    try:
        html = await fetcher.fetch(
            candidate.source_url,
            render_mode=candidate.render_mode,
            user_agent=candidate.user_agent,
            encoding=candidate.encoding,
        )
    except Exception as e:
        return _render("_items_preview.html", request, items=[], top_error=f"fetch error: {e}")
    try:
        extracted = run_extract(candidate, html)
    except Exception as e:
        return _render("_items_preview.html", request, items=[], top_error=f"extract error: {e}")
    if not extracted:
        return _render(
            "_items_preview.html",
            request,
            items=[],
            top_error="no items matched (selector/pattern wrong, or page may need browser mode)",
        )
    rendered = render_items(candidate, extracted[:5])
    return _render("_items_preview.html", request, items=rendered, top_error=None)


@app.post("/feeds/{slug}/refresh")
async def feed_refresh(slug: str, request: Request) -> Response:
    redirect = _editor_or_redirect(request)
    if redirect:
        return redirect
    conn = _conn(request)
    feed = db.get_feed_by_slug(conn, slug)
    if feed is None:
        return Response(status_code=404)
    await refresh_one(conn, _fetcher(request), feed.id)
    return RedirectResponse(f"/feeds/{slug}/edit", status_code=303)


@app.post("/feeds/{slug}/delete")
def feed_delete(slug: str, request: Request) -> Response:
    redirect = _editor_or_redirect(request)
    if redirect:
        return redirect
    conn = _conn(request)
    feed = db.get_feed_by_slug(conn, slug)
    if feed is None:
        return Response(status_code=404)
    db.delete_feed(conn, feed.id)
    return RedirectResponse("/", status_code=303)


@app.get("/feeds/{slug}", response_class=HTMLResponse)
def feed_detail(slug: str, request: Request) -> Response:
    conn = _conn(request)
    feed = db.get_feed_by_slug(conn, slug)
    if feed is None:
        return Response(status_code=404)
    items = db.list_items(conn, feed.id, limit=20)
    cfg = _cfg(request)
    return _render(
        "feed_detail.html",
        request,
        feed=feed,
        items=items,
        xml_url=feed_self_url(cfg.base_url, feed.slug),
    )
