"""Сбор новостей из RSS-лент и Hacker News за последние N часов."""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import urlparse

import feedparser
import httpx

import config
from models import Item

log = logging.getLogger(__name__)

HN_API = "https://hn.algolia.com/api/v1/search_by_date"


def _cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=config.WINDOW_HOURS)


def _is_blocked(url: str) -> bool:
    host = urlparse(url).netloc.lower().split(":")[0]
    # Сравниваем и по поддоменам: old.reddit.com должен блокироваться
    # правилом reddit.com, а не проскакивать мимо него
    return any(
        host == domain or host.endswith("." + domain)
        for domain in config.BLOCKED_DOMAINS
    )


def _entry_time(entry) -> datetime | None:
    """Достаёт дату публикации из записи RSS. Разные ленты кладут её по-разному."""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
    return None


_JUNK_RE = [re.compile(p, re.IGNORECASE) for p in config.JUNK_TITLE_PATTERNS]


def _clean(text: str, limit: int = 400) -> str:
    """Выкидывает HTML-теги и мнемоники из описания, подрезает длину."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    # Ленты часто отдают &#8217; и подобное — иначе это лезет в дайджест
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _is_junk(title: str) -> bool:
    """Гайды, подборки и распродажи — до скоринга, чтобы не жечь токены."""
    return any(pattern.search(title) for pattern in _JUNK_RE)


# --------------------------------------------------------------------- RSS


def _fetch_feed(name: str, url: str, cutoff: datetime) -> list[Item]:
    try:
        # feedparser сам ходит в сеть, но через httpx мы контролируем таймаут
        with httpx.Client(
            timeout=config.HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": config.USER_AGENT},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
    except Exception as exc:
        log.warning("RSS %s недоступен: %s", name, exc)
        return []

    items: list[Item] = []
    for entry in parsed.entries:
        published = _entry_time(entry)
        if published is None or published < cutoff:
            continue

        link = entry.get("link") or ""
        title = _clean(entry.get("title", ""), limit=300)
        if not link or not title or _is_blocked(link) or _is_junk(title):
            continue

        items.append(
            Item(
                title=title,
                url=link,
                source=name,
                published=published,
                summary=_clean(entry.get("summary", "")),
            )
        )

    log.info("RSS %-20s %d свежих", name, len(items))
    return items


def collect_rss(cutoff: datetime) -> list[Item]:
    """Обходит все ленты параллельно — иначе 25 лент это минуты ожидания."""
    items: list[Item] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [
            pool.submit(_fetch_feed, name, url, cutoff)
            for name, url in config.RSS_FEEDS
        ]
        for future in futures:
            items.extend(future.result())
    return items


# -------------------------------------------------------------- Hacker News


def _fetch_hn(
    tags: str,
    min_points: int,
    cutoff: datetime,
    query: str = "",
    hits: int | None = None,
) -> list[Item]:
    params = {
        "tags": tags,
        "numericFilters": f"created_at_i>{int(cutoff.timestamp())},points>{min_points}",
        "hitsPerPage": hits or config.HN_MAX_STORIES,
    }
    if query:
        params["query"] = query
    try:
        with httpx.Client(
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        ) as client:
            resp = client.get(HN_API, params=params)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
    except Exception as exc:
        log.warning("HN (%s) недоступен: %s", tags, exc)
        return []

    items: list[Item] = []
    for hit in hits:
        title = hit.get("title")
        if not title:
            continue

        discussion = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        # Ask HN и часть Show HN не имеют внешней ссылки — ведём на обсуждение
        url = hit.get("url") or discussion
        if _is_blocked(url):
            continue

        published = datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc)
        label = "Show HN" if "show_hn" in tags else "Hacker News"

        items.append(
            Item(
                title=_clean(title, limit=300),
                url=url,
                source=label,
                published=published,
                points=hit.get("points", 0),
                summary=f"Обсуждение на HN: {discussion}",
            )
        )

    log.info("HN  %-20s %d свежих", tags, len(items))
    return items


def collect_hn(cutoff: datetime) -> list[Item]:
    # Show HN судим мягче: там ценна новизна проекта, а не число апвоутов
    stories = _fetch_hn("story", config.HN_MIN_POINTS, cutoff)
    show = _fetch_hn("show_hn", config.HN_SHOW_MIN_POINTS, cutoff)
    return stories + show


def collect_hn_keywords(cutoff: datetime) -> list[Item]:
    """Поиск по ключевым словам — канал для инди-темы.

    Обычные медиа про доходы одиночных разработчиков не пишут, а на HN это
    регулярный жанр. Порог очков низкий: такие посты редко набирают много
    апвоутов, но именно они нужны.
    """
    found: list[Item] = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(
                _fetch_hn,
                "story",
                config.HN_KEYWORD_MIN_POINTS,
                cutoff,
                query=query,
                hits=config.HN_KEYWORD_HITS,
            ): query
            for query in config.HN_KEYWORD_QUERIES
        }
        for future, query in futures.items():
            items = future.result()
            if items:
                log.info("HN  запрос %-22s %d свежих", f'"{query}"', len(items))
            found.extend(items)

    return found


# -------------------------------------------------------------------- всё


def collect_all() -> list[Item]:
    cutoff = _cutoff()
    log.info("Собираю новости после %s UTC", cutoff.strftime("%Y-%m-%d %H:%M"))

    items = collect_rss(cutoff) + collect_hn(cutoff) + collect_hn_keywords(cutoff)

    # Схлопываем совпадения по точному URL — до умной дедупликации
    by_url: dict[str, Item] = {}
    for item in items:
        by_url.setdefault(item.url, item)

    result = sorted(by_url.values(), key=lambda i: i.published, reverse=True)
    log.info("Всего собрано: %d уникальных ссылок", len(result))
    return result
