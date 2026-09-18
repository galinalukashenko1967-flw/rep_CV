import sqlite3
from contextlib import contextmanager

from bot.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    keywords TEXT DEFAULT '',
    cv_path TEXT DEFAULT NULL,
    cv_text TEXT DEFAULT NULL,
    location TEXT DEFAULT ''
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


def filter_unseen(telegram_id: int, urls: list[str]) -> set[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT vacancy_url FROM seen_vacancies WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchall()
        seen = {r["vacancy_url"] for r in rows}
    return {u for u in urls if u not in seen}
