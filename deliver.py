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


def _plural(count: int, one: str, few: str, many: str) -> str:
    """«1 материал», «2 материала», «5 материалов»."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def _render_items(items: list[Item], start_num: int = 1) -> list[str]:
    parts = []
    for num, item in enumerate(items, start=start_num):
        card = item.card
        url = _esc(item.url)

        block = [f'<b>{num:02d}  {_esc(card["headline"])}</b>']

        if card["what"]:
            block.append(_esc(card["what"]))
        if card["why"]:
            # blockquote рисует вертикальную полоску слева и подложку —
            # это весь доступный визуальный акцент
            block.append(
                f"<blockquote>Почему важно: {_esc(card['why'])}</blockquote>"
            )

        sources = ", ".join(item.all_sources[:3])
        block.append(f'<a href="{url}">{_esc(sources)}</a>')

        # Пустая строка между всеми частями пункта: в Telegram нет отступов,
        # и без неё заголовок, текст, цитата и ссылка слипаются в стену
        parts.append("\n\n".join(block))
        parts.append("")
    return parts


def format_digest(
    items: list[Item],
    extras: list[Item] | None = None,
    startups: list[Item] | None = None,
) -> str:
    # Оба раздела необязательны, поэтому нормализуем до списков сразу:
    # иначе len(None) роняет сборку в день, когда стартапов не нашлось
    startups = startups or []
    items = items or []

    today = datetime.now()
    date_str = f"{today.day} {MONTHS[today.month - 1]}"

    if not items and not startups:
        return (
            f"<b>Дайджест за {date_str}</b>\n\n"
            "Сегодня нечего показать — ничего существенного по твоим темам "
            "за сутки не вышло."
        )

    total = len(items) + len(startups)
    parts = [
        f"<b>☕ Дайджест за {date_str}</b>",
        f"<i>{total} {_plural(total, 'материал', 'материала', 'материалов')} · "
        f"{len(items)} в главном, {len(startups)} про стартапы</i>",
        "",
    ]

    if items:
        parts.append("<b>📰 ГЛАВНОЕ</b>")
        parts.append("")
        parts.extend(_render_items(items))

    if startups:
        parts.append("<b>🚀 СТАРТАПЫ И НОВЫЕ ИДЕИ</b>")
        parts.append("")
        # Сквозная нумерация: так понятно, сколько всего прочитано
        parts.extend(_render_items(startups, start_num=len(items) + 1))

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


def _credentials() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(
            "Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID — проверь .env"
        )
    return token, chat_id


def send_to_telegram(text: str) -> None:
    token, chat_id = _credentials()
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
