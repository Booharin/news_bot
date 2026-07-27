"""История отправленного — чтобы одна и та же новость не пришла дважды.

SQLite без ORM: одна таблица, три запроса. Postgres тут не нужен.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Путь к базе можно переопределить: удобно для тестов и для деплоя,
# где база лежит на примонтированном томе
DB_PATH = Path(os.environ.get("DIGEST_DB", Path(__file__).parent / "digest.db"))

# Сколько дней помнить отправленное. Дольше нет смысла: тема успевает устареть.
RETENTION_DAYS = 14


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sent (
            url        TEXT PRIMARY KEY,
            title_norm TEXT NOT NULL,
            sent_at    TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_at ON sent(sent_at)")
    conn.commit()
    return conn


def already_sent(urls: list[str], titles_norm: list[str]) -> set[str]:
    """Возвращает URL-ы, которые уже уходили в дайджест.

    Проверяем и по ссылке, и по нормализованному заголовку — одно событие
    часто всплывает на следующий день у другого издания с другой ссылкой.
    """
    if not urls:
        return set()

    # closing(), а не просто with: контекст-менеджер sqlite3 управляет
    # транзакцией, но соединение не закрывает
    with closing(_connect()) as conn:
        placeholders = ",".join("?" * len(urls))
        rows = conn.execute(
            f"SELECT url FROM sent WHERE url IN ({placeholders})", urls
        ).fetchall()
        seen = {row[0] for row in rows}

        if titles_norm:
            placeholders = ",".join("?" * len(titles_norm))
            rows = conn.execute(
                f"SELECT url, title_norm FROM sent WHERE title_norm IN ({placeholders})",
                titles_norm,
            ).fetchall()
            sent_titles = {row[1] for row in rows}
            for url, title in zip(urls, titles_norm):
                if title in sent_titles:
                    seen.add(url)

    return seen


def mark_sent(pairs: list[tuple[str, str]]) -> None:
    """pairs — список (url, нормализованный заголовок)."""
    if not pairs:
        return
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO sent (url, title_norm, sent_at) VALUES (?, ?, ?)",
            [(url, title, now) for url, title in pairs],
        )
        conn.commit()


def prune() -> None:
    """Чистит старые записи, чтобы база не росла вечно."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM sent WHERE sent_at < ?", (cutoff,))
        conn.commit()
