"""Форматирование дайджеста и отправка в Telegram."""

from __future__ import annotations

import html
import logging
import os
from datetime import datetime

import httpx

from models import Item

log = logging.getLogger(__name__)

# Лимит Telegram — 4096 символов на сообщение, берём с запасом
MAX_MESSAGE = 3800

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def format_digest(items: list[Item], extras: list[Item] | None = None) -> str:
    today = datetime.now()
    date_str = f"{today.day} {MONTHS[today.month - 1]}"

    if not items:
        return (
            f"<b>Дайджест за {date_str}</b>\n\n"
            "Сегодня нечего показать — ничего существенного по твоим темам "
            "за сутки не вышло."
        )

    parts = [f"<b>Дайджест за {date_str}</b>", ""]

    for num, item in enumerate(items, start=1):
        card = item.card
        block = [f"<b>{num}. {_esc(card['headline'])}</b>"]

        if card["what"]:
            block.append(_esc(card["what"]))
        if card["why"]:
            block.append(f"<i>Почему важно:</i> {_esc(card['why'])}")

        sources = ", ".join(item.all_sources[:3])
        block.append(f'<a href="{_esc(item.url)}">{_esc(sources)}</a>')

        parts.append("\n".join(block))
        parts.append("")

    if extras:
        titles = "; ".join(_esc(i.title) for i in extras[:4])
        parts.append(f"<i>Ещё мельком:</i> {titles}")

    return "\n".join(parts).strip()


def _split(text: str) -> list[str]:
    """Режет длинный дайджест по границам пунктов, а не по символам."""
    if len(text) <= MAX_MESSAGE:
        return [text]

    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > MAX_MESSAGE and current:
            chunks.append(current)
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_to_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(
            "Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID — проверь .env"
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for chunk in _split(text):
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        if resp.status_code != 200:
            log.error("Telegram вернул %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()

    log.info("Дайджест отправлен в Telegram")
