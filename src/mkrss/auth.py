import secrets

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import Config


def _serializer(cfg: Config) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(cfg.session_secret, salt="mkrss.session")


def issue_session(cfg: Config, response: Response) -> None:
    token = _serializer(cfg).dumps({"v": 1})
    response.set_cookie(
        cfg.session_cookie_name,
        token,
        max_age=cfg.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=cfg.base_url.startswith("https://"),
    )


def clear_session(cfg: Config, response: Response) -> None:
    response.delete_cookie(cfg.session_cookie_name)


def is_authenticated(cfg: Config, request: Request) -> bool:
    token = request.cookies.get(cfg.session_cookie_name)
    if not token:
        return False
    try:
        _serializer(cfg).loads(token, max_age=cfg.session_max_age_seconds)
        return True
    except BadSignature:
        return False


def verify_password(cfg: Config, supplied: str) -> bool:
    if not cfg.editor_password:
        return False
    return secrets.compare_digest(cfg.editor_password.encode(), supplied.encode())


def require_editor(cfg: Config):
    def dependency(request: Request) -> None:
        if not cfg.editor_password:
            raise HTTPException(status_code=404)
        if not is_authenticated(cfg, request):
            raise HTTPException(status_code=303, headers={"location": "/login"})

    return dependency
