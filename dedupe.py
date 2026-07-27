"""Схлопывание разных статей об одном событии в один пункт.

Без эмбеддингов: нормализация заголовка плюс мера Жаккара по значимым словам
ловит подавляющее большинство дублей и не требует ни модели, ни векторной базы.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse, urlunparse

from models import Item

log = logging.getLogger(__name__)

# Порог схожести заголовков, выше которого считаем, что событие одно
SIMILARITY_THRESHOLD = 0.6

# Слова, которые не несут смысла при сравнении заголовков
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "it", "its", "this", "that", "these", "those", "new", "now",
    "says", "said", "how", "why", "what", "who", "will", "can", "has",
    "have", "after", "over", "into", "about", "more", "you", "your",
}


def normalize_title(title: str) -> str:
    """Заголовок в канонический вид: нижний регистр, только буквы и цифры."""
    title = title.lower()
    # Убираем хвост издания: "Заголовок | TechCrunch", "Заголовок - The Verge"
    title = re.split(r"\s+[|—–-]\s+(?=[A-Za-z\s]{2,25}$)", title)[0]
    title = re.sub(r"[^a-z0-9а-яё\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def canonical_url(url: str) -> str:
    """Отрезает utm-метки и якоря, чтобы одинаковые ссылки совпали."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return urlunparse(("https", netloc, path, "", "", ""))


def _tokens(title: str) -> set[str]:
    words = normalize_title(title).split()
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    # Не Жаккар в чистом виде, а деление на меньшее множество: короткий заголовок
    # агентства и развёрнутый заголовок издания описывают одно и то же событие
    return intersection / min(len(a), len(b))


def _rank(item: Item) -> tuple:
    """Кого выбрать представителем кластера.

    Приоритет у первоисточника (официальные блоги компаний), затем у HN
    с большим числом очков, затем у более раннего материала.
    """
    primary_sources = {
        "OpenAI", "Anthropic", "Google DeepMind", "Google Research",
        "GitHub Blog", "Cloudflare Blog", "Stripe Blog", "Vercel Blog",
        "Hugging Face", "Netflix Tech",
    }
    is_primary = item.source in primary_sources
    return (is_primary, item.points, -item.published.timestamp())


def deduplicate(items: list[Item]) -> list[Item]:
    """Группирует статьи об одном событии, возвращает по одному представителю."""
    # Сначала точные совпадения по канонической ссылке
    by_url: dict[str, list[Item]] = {}
    for item in items:
        by_url.setdefault(canonical_url(item.url), []).append(item)

    candidates: list[Item] = []
    for group in by_url.values():
        group.sort(key=_rank, reverse=True)
        best = group[0]
        best.duplicates = group[1:]
        candidates.append(best)

    # Затем схожие заголовки
    token_cache = {id(item): _tokens(item.title) for item in candidates}
    clusters: list[list[Item]] = []

    for item in candidates:
        item_tokens = token_cache[id(item)]
        placed = False
        for cluster in clusters:
            head_tokens = token_cache[id(cluster[0])]
            if _similarity(item_tokens, head_tokens) >= SIMILARITY_THRESHOLD:
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])

    result: list[Item] = []
    for cluster in clusters:
        cluster.sort(key=_rank, reverse=True)
        best = cluster[0]
        for other in cluster[1:]:
            best.duplicates.append(other)
            best.duplicates.extend(other.duplicates)
        result.append(best)

    log.info("Дедупликация: %d -> %d событий", len(items), len(result))
    return result
