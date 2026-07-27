"""Написание карточек новостей: заголовок, что произошло, почему важно."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import httpx
import trafilatura

import config
import llm
from models import Item

log = logging.getLogger(__name__)

MAX_ARTICLE_CHARS = 6000

SYSTEM = """Ты пишешь карточки новостей для утреннего дайджеста.

Жёсткие правила:
1. Пиши по-русски, сухо и по делу. Никаких восторгов, маркетингового языка
   и слов вроде "революционный", "прорывной", "меняет всё".
2. Если в новости фигурирует стартап или малоизвестная компания — обязательно
   объясни в скобках в двух-трёх словах, чем она занимается. Читатель не должен
   ничего гуглить. Пример: "Etched (ASIC-чипы под трансформеры) привлёк $300 млн".
   Для общеизвестных компаний (Google, Apple, OpenAI) пояснение не нужно.
3. Поле why заполняй ТОЛЬКО если есть содержательное следствие. Если новость
   просто любопытная, но ни на что не влияет — верни для why пустую строку.
   Никогда не выдумывай значимость и не пиши banality вроде
   "это показывает, что рынок развивается".
4. Опирайся только на текст статьи. Не додумывай факты, которых там нет."""

PROMPT = """Напиши карточку новости для дайджеста.

Источник: {source}
Заголовок оригинала: {title}

Текст статьи:
{text}

Верни ТОЛЬКО JSON:
{{
  "headline": "заголовок своими словами по-русски, одно предложение без кликбейта",
  "what": "что произошло — 1-2 предложения с конкретикой: цифры, названия, версии",
  "why": "почему это важно — одно предложение, или пустая строка если сказать нечего"
}}"""


def _fetch_article(item: Item) -> None:
    """Тянет полный текст статьи. Если не вышло — работаем по описанию из ленты."""
    try:
        with httpx.Client(
            timeout=config.HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": config.USER_AGENT},
        ) as client:
            resp = client.get(item.url)
            resp.raise_for_status()

        text = trafilatura.extract(
            resp.text, include_comments=False, include_tables=False
        )
        item.article_text = (text or "")[:MAX_ARTICLE_CHARS]
    except Exception as exc:
        log.warning("Не скачал %s: %s", item.url, exc)
        item.article_text = ""

    if not item.article_text:
        item.article_text = item.summary


def fetch_articles(items: list[Item]) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_fetch_article, items))


def _write_card(item: Item) -> None:
    if not item.article_text.strip():
        # Совсем нечего читать — обойдёмся оригинальным заголовком
        item.card = ""
        return

    prompt = PROMPT.format(
        source=item.source, title=item.title, text=item.article_text
    )
    try:
        result = llm.ask_json(
            config.WRITING_MODEL, prompt, max_tokens=2048, system=SYSTEM
        )
        item.card = {
            "headline": str(result.get("headline", item.title)).strip(),
            "what": str(result.get("what", "")).strip(),
            "why": str(result.get("why", "")).strip(),
        }
    except Exception as exc:
        log.error("Карточка не написана для %s: %s", item.url, exc)
        item.card = ""


def write_cards(items: list[Item]) -> list[Item]:
    """Пишет карточки параллельно и отбрасывает те, что не получились."""
    fetch_articles(items)

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(_write_card, items))

    good = [i for i in items if i.card]
    log.info("Карточек написано: %d из %d", len(good), len(items))
    return good
