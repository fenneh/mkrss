from fastapi.responses import Response

from mkrss.auth import clear_session, is_authenticated, issue_session, verify_password
from mkrss.config import Config


def _cfg(**overrides) -> Config:
    defaults = dict(
        db_path="data/test.sqlite3",
        base_url="http://localhost:8000",
        editor_password="correct-password",
        session_secret="test-secret-key",
    )
    defaults.update(overrides)
    return Config(**defaults)


class _FakeRequest:
    def __init__(self, cookies: dict) -> None:
        self.cookies = cookies


def _extract_cookie(response: Response, name: str) -> str | None:
    for header_val in response.raw_headers:
        key, val = header_val
        if key == b"set-cookie":
            decoded = val.decode()
            for part in decoded.split(";"):
                part = part.strip()
                if part.startswith(f"{name}="):
                    return part[len(f"{name}=") :]
    return None


def test_verify_password_correct():
    assert verify_password(_cfg(), "correct-password")


def test_verify_password_wrong():
    assert not verify_password(_cfg(), "wrong")


def test_verify_password_empty_supplied():
    assert not verify_password(_cfg(), "")


def test_verify_password_no_password_configured():
    cfg = _cfg(editor_password=None)
    assert not verify_password(cfg, "")
    assert not verify_password(cfg, "anything")


def test_is_authenticated_no_cookie():
    assert not is_authenticated(_cfg(), _FakeRequest({}))


def test_is_authenticated_invalid_cookie():
    req = _FakeRequest({"mkrss_session": "garbage"})
    assert not is_authenticated(_cfg(), req)


def test_is_authenticated_cookie_from_wrong_secret():
    cfg_a = _cfg(session_secret="secret-a")
    cfg_b = _cfg(session_secret="secret-b")
    resp = Response()
    issue_session(cfg_a, resp)
    token = _extract_cookie(resp, cfg_a.session_cookie_name)
    assert token is not None
    req = _FakeRequest({cfg_b.session_cookie_name: token})
    assert not is_authenticated(cfg_b, req)


def test_issue_then_is_authenticated():
    cfg = _cfg()
    resp = Response()
    issue_session(cfg, resp)
    token = _extract_cookie(resp, cfg.session_cookie_name)
    assert token is not None
    req = _FakeRequest({cfg.session_cookie_name: token})
    assert is_authenticated(cfg, req)


def test_clear_session_removes_cookie():
    cfg = _cfg()
    resp = Response()
    issue_session(cfg, resp)
    token = _extract_cookie(resp, cfg.session_cookie_name)
    assert token is not None

    resp2 = Response()
    clear_session(cfg, resp2)
    cleared = _extract_cookie(resp2, cfg.session_cookie_name)
    assert cleared == '""' or cleared == "" or cleared is None or len(cleared) == 0


def test_secure_flag_set_for_https_base_url():
    cfg = _cfg(base_url="https://example.com")
    resp = Response()
    issue_session(cfg, resp)
    raw = b"".join(v for k, v in resp.raw_headers if k == b"set-cookie")
    assert b"secure" in raw.lower()


def test_secure_flag_not_set_for_http_base_url():
    cfg = _cfg(base_url="http://localhost:8000")
    resp = Response()
    issue_session(cfg, resp)
    raw = b"".join(v for k, v in resp.raw_headers if k == b"set-cookie")
    assert b"secure" not in raw.lower()
