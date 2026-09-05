"""Форматирование дайджеста и отправка в Telegram."""

from __future__ import annotations

import html
import logging
import os
import time
from datetime import datetime

import httpx

from models import Item

log = logging.getLogger(__name__)

# Лимит Telegram — 4096 символов на сообщение, берём с запасом
MAX_MESSAGE = 3800

# Пауза между сообщениями. Telegram допускает примерно одно в секунду на чат,
# берём с небольшим запасом — весь выпуск уйдёт меньше чем за минуту.
SEND_DELAY = 1.2

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


def _render_item(item: Item, num: int) -> str:
    card = item.card
    url = _esc(item.url)

    # Единственный способ получить цвет в Telegram — ссылка: клиент красит
    # её синим. Поэтому номер сам по себе кликабельный и ведёт на статью.
    block = [f'<a href="{url}">{num:02d}</a>  <b>{_esc(card["headline"])}</b>']

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

    return "\n".join(block)


def build_messages(
    items: list[Item],
    extras: list[Item] | None = None,
    startups: list[Item] | None = None,
    indie: list[Item] | None = None,
) -> list[str]:
    """Каждая новость — отдельное сообщение.

    Так её можно переслать, процитировать или сохранить в «Избранное»
    по отдельности, чего не позволял общий блок.
    """
    # Оба раздела необязательны, поэтому нормализуем до списков сразу:
    # иначе len(None) роняет сборку в день, когда стартапов не нашлось
    startups = startups or []
    indie = indie or []
    items = items or []

    today = datetime.now()
    date_str = f"{today.day} {MONTHS[today.month - 1]}"

    if not items and not startups and not indie:
        return [
            f"<b>Дайджест за {date_str}</b>\n\n"
            "Сегодня нечего показать — ничего существенного по твоим темам "
            "за сутки не вышло."
        ]

    total = len(items) + len(startups) + len(indie)
    messages = [
        f"<b>☕ Дайджест за {date_str}</b>\n"
        f"<i>{total} {_plural(total, 'материал', 'материала', 'материалов')} · "
        f"{len(items)} в главном, {len(startups)} про стартапы, "
        f"{len(indie)} про инди</i>"
    ]

    # Сквозная нумерация через все разделы: видно общий объём прочитанного
    number = 1

    if items:
        messages.append("<b>📰 ГЛАВНОЕ</b>")
        messages.extend(_render_item(item, n) for n, item in enumerate(items, number))
        number += len(items)

    if startups:
        messages.append("<b>🚀 СТАРТАПЫ И НОВЫЕ ИДЕИ</b>")
        messages.extend(
            _render_item(item, n) for n, item in enumerate(startups, number)
        )
        number += len(startups)

    if indie:
        messages.append("<b>💰 ИНДИ И ЗАРАБОТОК НА ПРОДУКТАХ</b>")
        messages.extend(
            _render_item(item, n) for n, item in enumerate(indie, number)
        )
        number += len(indie)

    if extras:
        titles = "; ".join(_esc(i.title) for i in extras[:4])
        messages.append(f"<i>Ещё мельком:</i> {titles}")

    return messages


def format_digest(
    items: list[Item],
    extras: list[Item] | None = None,
    startups: list[Item] | None = None,
    indie: list[Item] | None = None,
) -> str:
    """Весь выпуск одним текстом — для --dry-run и тестов."""
    return "\n\n".join(build_messages(items, extras, startups, indie))


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


def _post(client, url: str, payload: dict) -> None:
    """Одна отправка с обработкой лимита частоты.

    Telegram отвечает 429 и полем retry_after, если сообщения идут слишком
    часто. Ждём ровно столько, сколько просят, и повторяем.
    """
    for attempt in range(3):
        resp = client.post(url, json=payload)
        if resp.status_code == 200:
            return

        if resp.status_code == 429:
            wait = resp.json().get("parameters", {}).get("retry_after", 5)
            log.warning("Telegram просит подождать %s с", wait)
            time.sleep(wait + 1)
            continue

        log.error("Telegram вернул %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()

    raise RuntimeError("Telegram не принял сообщение после трёх попыток")


def send_to_telegram(messages: list[str] | str) -> None:
    """Отправляет выпуск по сообщению на новость.

    Звук только у первого сообщения: сорок уведомлений подряд — это пытка,
    а одно с заголовком выпуска ровно то, что нужно.
    """
    if isinstance(messages, str):
        messages = [messages]

    token, chat_id = _credentials()
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    sent = 0
    with httpx.Client(timeout=30) as client:
        for index, message in enumerate(messages):
            for chunk in _split(message):
                _post(
                    client,
                    url,
                    {
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                        "disable_notification": index > 0,
                    },
                )
                sent += 1
                # Telegram держит примерно одно сообщение в секунду на чат;
                # без паузы пачка из сорока штук упрётся в 429
                if index < len(messages) - 1:
                    time.sleep(SEND_DELAY)

    log.info("Отправлено сообщений в Telegram: %d", sent)
