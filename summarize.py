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

# Минимальная длина текста, при которой есть смысл писать карточку.
# Если статью не удалось скачать (paywall, 403), в article_text остаётся
# огрызок из ленты — модель на нём сочиняет пустышку вида "на Hacker News
# обсуждают материал о...". Такие пункты лучше выбросить целиком.
MIN_ARTICLE_CHARS = 300

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
  "headline": "заголовок по-русски, НЕ ДЛИННЕЕ 80 СИМВОЛОВ, без кликбейта",
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
        # Заглушка со ссылкой на обсуждение — не текст статьи, а мусор
        if item.summary.startswith("Обсуждение на HN"):
            item.article_text = ""
        else:
            item.article_text = item.summary


def fetch_articles(items: list[Item]) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_fetch_article, items))


def _write_card(item: Item) -> None:
    if len(item.article_text.strip()) < MIN_ARTICLE_CHARS:
        # Читать нечего — карточка получилась бы пустой по смыслу
        log.info("Пропущено, нет текста статьи: %s", item.url)
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


TRANSLATE_PROMPT = """Переведи заголовки новостей на русский язык.

{items}

Пиши коротко и по делу, без кликбейта. Названия компаний и продуктов оставляй
латиницей. Верни ТОЛЬКО JSON вида {{"titles": ["перевод 1", "перевод 2"]}}
в том же порядке и том же количестве."""


def translate_titles(items: list[Item]) -> None:
    """Переводит заголовки для блока «Ещё мельком».

    Один дешёвый вызов на весь блок: писать для них полные карточки незачем,
    но и оставлять английские строки в русском дайджесте не хочется.
    """
    if not items:
        return

    listing = "\n".join(f"{i}. {item.title}" for i, item in enumerate(items, 1))

    try:
        titles = llm.ask_json(
            config.SCORING_MODEL,
            TRANSLATE_PROMPT.format(items=listing),
            max_tokens=2048,
        )
    except Exception as exc:
        log.warning("Заголовки не переведены, останутся как есть: %s", exc)
        return

    if not isinstance(titles, list) or len(titles) != len(items):
        log.warning("Перевод вернул %s строк вместо %d", len(titles), len(items))
        return

    for item, title in zip(items, titles):
        if isinstance(title, str) and title.strip():
            item.title = title.strip()


def write_cards(items: list[Item]) -> list[Item]:
    """Пишет карточки параллельно и отбрасывает те, что не получились."""
    fetch_articles(items)

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(_write_card, items))

    good = [i for i in items if i.card]
    log.info("Карточек написано: %d из %d", len(good), len(items))
    return good
