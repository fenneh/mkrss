import pytest
from fastapi.testclient import TestClient

from mkrss.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("EDITOR_PASSWORD", "test-password")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-key")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def disabled_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")
    monkeypatch.delenv("EDITOR_PASSWORD", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "test-secret-key")
    with TestClient(app) as c:
        yield c


def _login(client) -> None:
    resp = client.post("/login", data={"password": "test-password"}, follow_redirects=False)
    assert resp.status_code == 303


def _create_feed(client, slug_seed: str = "example feed") -> str:
    resp = client.post(
        "/feeds",
        data={
            "slug_seed": slug_seed,
            "source_url": "https://example.com",
            "title": "Example Feed",
            "extraction_mode": "css",
            "render_mode": "http",
            "item_selector": "article",
            "field_name": ["title"],
            "field_source": ["item"],
            "field_selector": ["h2"],
            "field_attribute": [""],
            "field_transform": [""],
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.endswith("/edit")
    return location.removeprefix("/feeds/").removesuffix("/edit")


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_unknown_feed_xml_404(client):
    resp = client.get("/feeds/does-not-exist.xml")
    assert resp.status_code == 404


def test_index_redirects_when_not_authenticated(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_login_wrong_password(client):
    resp = client.post("/login", data={"password": "wrong"}, follow_redirects=False)
    assert resp.status_code == 401


def test_login_then_index_accessible(client):
    _login(client)
    resp = client.get("/")
    assert resp.status_code == 200


def test_logout_clears_session(client):
    _login(client)
    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    resp2 = client.get("/", follow_redirects=False)
    assert resp2.status_code == 303
    assert resp2.headers["location"] == "/login"


def test_disabled_when_no_editor_password(disabled_client):
    resp = disabled_client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/disabled"

    resp2 = disabled_client.get("/login", follow_redirects=False)
    assert resp2.status_code == 303
    assert resp2.headers["location"] == "/disabled"


def test_feed_create_and_edit_flow(client):
    _login(client)
    slug = _create_feed(client)

    resp = client.get(f"/feeds/{slug}/edit")
    assert resp.status_code == 200

    resp2 = client.get(f"/feeds/{slug}")
    assert resp2.status_code == 200

    xml_resp = client.get(f"/feeds/{slug}.xml")
    assert xml_resp.status_code == 200
    assert "application/rss+xml" in xml_resp.headers["content-type"]


def test_feed_edit_requires_auth(client):
    resp = client.get("/feeds/some-feed/edit", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_feed_edit_unknown_slug_404(client):
    _login(client)
    resp = client.get("/feeds/does-not-exist/edit")
    assert resp.status_code == 404


def test_feed_new_form_renders(client):
    _login(client)
    resp = client.get("/feeds/new")
    assert resp.status_code == 200


def test_feed_save_updates_title(client):
    _login(client)
    slug = _create_feed(client)
    resp = client.post(
        f"/feeds/{slug}",
        data={
            "slug_seed": slug,
            "source_url": "https://example.com",
            "title": "Renamed Feed",
            "extraction_mode": "css",
            "render_mode": "http",
            "item_selector": "article",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    detail = client.get(f"/feeds/{slug}")
    assert "Renamed Feed" in detail.text


def test_feed_save_unknown_slug_404(client):
    _login(client)
    resp = client.post("/feeds/does-not-exist", data={"title": "x"})
    assert resp.status_code == 404


def test_feed_delete(client):
    _login(client)
    slug = _create_feed(client)
    resp = client.post(f"/feeds/{slug}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    resp2 = client.get(f"/feeds/{slug}")
    assert resp2.status_code == 404


def test_feed_delete_unknown_slug_404(client):
    _login(client)
    resp = client.post("/feeds/does-not-exist/delete")
    assert resp.status_code == 404


def test_feed_refresh_unknown_slug_404(client):
    _login(client)
    resp = client.post("/feeds/does-not-exist/refresh")
    assert resp.status_code == 404


def test_feed_test_unknown_slug_404(client):
    _login(client)
    resp = client.post("/feeds/does-not-exist/test", data={})
    assert resp.status_code == 404


def test_feed_test_fetch_error(client):
    _login(client)
    slug = _create_feed(client)
    resp = client.post(
        f"/feeds/{slug}/test",
        data={
            "source_url": "http://127.0.0.1:1/unreachable",
            "extraction_mode": "css",
            "render_mode": "http",
            "item_selector": "article",
        },
    )
    assert resp.status_code == 200
    assert "fetch error" in resp.text
