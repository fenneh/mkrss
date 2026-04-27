import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    db_path: str
    base_url: str
    editor_password: str | None
    session_secret: str
    session_cookie_name: str = "mkrss_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 30


def load() -> Config:
    return Config(
        db_path=os.environ.get("DB_PATH", "data/mkrss.sqlite3"),
        base_url=os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/"),
        editor_password=os.environ.get("EDITOR_PASSWORD") or None,
        session_secret=os.environ.get("SESSION_SECRET", "dev-secret-change-me"),
    )
