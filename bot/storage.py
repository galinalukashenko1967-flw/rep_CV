import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict

from bot.config import DB_PATH
from bot.sources import Vacancy

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    keywords TEXT DEFAULT '',
    cv_path TEXT DEFAULT NULL,
    cv_text TEXT DEFAULT NULL,
    location TEXT DEFAULT '',
    last_results TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS seen_vacancies (
    telegram_id INTEGER NOT NULL,
    vacancy_url TEXT NOT NULL,
    PRIMARY KEY (telegram_id, vacancy_url)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Lightweight migration for DBs created before cv_text existed
        # (e.g. an already-deployed Railway instance) -- CREATE TABLE IF
        # NOT EXISTS above won't add columns to an existing table.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "cv_text" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN cv_text TEXT DEFAULT NULL")
        if "last_results" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN last_results TEXT DEFAULT NULL")


def get_user(telegram_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return dict(row) if row else None


def ensure_user(telegram_id: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (telegram_id,)
        )


def set_keywords(telegram_id: int, keywords: list[str]):
    ensure_user(telegram_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET keywords = ? WHERE telegram_id = ?",
            (",".join(keywords), telegram_id),
        )


def get_keywords(telegram_id: int) -> list[str]:
    user = get_user(telegram_id)
    if not user or not user["keywords"]:
        return []
    return [k.strip() for k in user["keywords"].split(",") if k.strip()]


def set_cv_path(telegram_id: int, cv_path: str):
    ensure_user(telegram_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET cv_path = ? WHERE telegram_id = ?",
            (cv_path, telegram_id),
        )


def set_cv_text(telegram_id: int, cv_text: str):
    ensure_user(telegram_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET cv_text = ? WHERE telegram_id = ?",
            (cv_text, telegram_id),
        )


def get_cv_text(telegram_id: int) -> str | None:
    user = get_user(telegram_id)
    return (user or {}).get("cv_text") or None


def set_location(telegram_id: int, location: str):
    ensure_user(telegram_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET location = ? WHERE telegram_id = ?",
            (location, telegram_id),
        )


def mark_seen(telegram_id: int, urls: list[str]):
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO seen_vacancies (telegram_id, vacancy_url) VALUES (?, ?)",
            [(telegram_id, u) for u in urls],
        )


def clear_seen(telegram_id: int) -> int:
    """Forget every vacancy already shown to this user, so the next
    /search can show them all again (e.g. after switching keywords or
    city, if they want a fresh full list rather than only what's new)."""
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM seen_vacancies WHERE telegram_id = ?", (telegram_id,)
        )
        return cursor.rowcount


def set_last_results(telegram_id: int, scored: list[tuple[Vacancy, int, str]]):
    """Persists the last /search results (vacancy, percent, reasoning) so
    "type a number" / "next vacancy" keeps working across bot restarts --
    an in-memory-only cache used to silently lose this on every redeploy,
    which made a bare "1" fall through to overwriting keywords instead."""
    ensure_user(telegram_id)
    payload = json.dumps(
        [[asdict(v), percent, detail] for v, percent, detail in scored]
    )
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET last_results = ? WHERE telegram_id = ?",
            (payload, telegram_id),
        )


def get_last_results(telegram_id: int) -> list[tuple[Vacancy, int, str]]:
    user = get_user(telegram_id)
    raw = (user or {}).get("last_results")
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [(Vacancy(**v), percent, detail) for v, percent, detail in data]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def get_stats() -> dict:
    """Basic usage counts for the /stats admin command -- how many people
    have ever started the bot (one row per unique telegram_id) and how far
    they got through setup."""
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        with_cv = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE cv_text IS NOT NULL AND cv_text != ''"
        ).fetchone()["n"]
        with_keywords = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE keywords IS NOT NULL AND keywords != ''"
        ).fetchone()["n"]
        with_location = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE location IS NOT NULL AND location != ''"
        ).fetchone()["n"]
        searched = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE last_results IS NOT NULL AND last_results != ''"
        ).fetchone()["n"]
    return {
        "total": total,
        "with_cv": with_cv,
        "with_keywords": with_keywords,
        "with_location": with_location,
        "searched": searched,
    }


def filter_unseen(telegram_id: int, urls: list[str]) -> set[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT vacancy_url FROM seen_vacancies WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchall()
        seen = {r["vacancy_url"] for r in rows}
    return {u for u in urls if u not in seen}
