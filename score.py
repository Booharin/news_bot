"""Оценка новостей по профилю интересов.

Заголовки уходят в модель батчами: 500 отдельных запросов стоили бы дорого
и заняли бы минуты, один запрос на 40 заголовков — центы и секунды.
"""

from __future__ import annotations

import logging

import config
import llm
from models import Item

log = logging.getLogger(__name__)

SYSTEM = """Ты отбираешь новости для утреннего дайджеста одного конкретного человека.
Твоя задача — честно оценить, насколько каждая новость ему интересна.

Будь строгим. Большинство новостей в ленте — проходные: минорные обновления,
пересказы чужих материалов, пресс-релизы без содержания, статьи-списки.
Такие новости должны получать 0-3 балла. Балл 8 и выше — это событие,
о котором человек будет рад узнать и, возможно, расскажет коллегам.

Оценивай по совокупности:
- попадание в профиль интересов (главный критерий)
- значимость: что-то реально произошло или появилось, а не заявлено о планах
- новизна: это новый факт, а не очередной комментарий к старому событию
- конкретность: есть цифры, названия, детали — а не общие рассуждения"""

PROMPT = """Профиль интересов человека:
{profile}

Оцени каждую новость из списка баллом от 0 до 10.

{items}

Верни ТОЛЬКО JSON вида:
{{"scores": [{{"id": 1, "score": 7, "reason": "краткое обоснование, до 10 слов"}}]}}

Обязательно верни запись для каждого id из списка."""


def _format_batch(items: list[Item], offset: int) -> str:
    lines = []
    for idx, item in enumerate(items, start=offset):
        line = f"{idx}. [{item.source}] {item.title}"
        if item.points:
            line += f" ({item.points} очков на HN)"
        if item.summary and not item.summary.startswith("Обсуждение на HN"):
            line += f"\n   {item.summary[:200]}"
        lines.append(line)
    return "\n".join(lines)


def score_items(items: list[Item]) -> list[Item]:
    """Проставляет score каждой новости и возвращает шортлист лучших."""
    if not items:
        return []

    scored_by_id: dict[int, dict] = {}

    for start in range(0, len(items), config.SCORING_BATCH_SIZE):
        batch = items[start : start + config.SCORING_BATCH_SIZE]
        prompt = PROMPT.format(
            profile=config.INTEREST_PROFILE,
            items=_format_batch(batch, offset=start + 1),
        )

        try:
            result = llm.ask_json(
                config.SCORING_MODEL, prompt, max_tokens=4096, system=SYSTEM
            )
        except Exception as exc:
            # Падение одного батча не должно ронять весь дайджест
            log.error("Батч %d не оценён: %s", start, exc)
            continue

        for entry in result:
            try:
                scored_by_id[int(entry["id"])] = entry
            except (KeyError, ValueError, TypeError):
                continue

        log.info("Оценено %d/%d", min(start + len(batch), len(items)), len(items))

    for idx, item in enumerate(items, start=1):
        entry = scored_by_id.get(idx)
        if entry:
            try:
                item.score = float(entry.get("score", 0))
            except (TypeError, ValueError):
                item.score = 0.0
            item.reason = str(entry.get("reason", ""))[:120]

    ranked = sorted(items, key=lambda i: i.score, reverse=True)
    shortlist = [i for i in ranked if i.score >= config.MIN_SCORE][
        : config.SHORTLIST_SIZE
    ]

    log.info(
        "Шортлист: %d новостей, баллы от %.1f до %.1f",
        len(shortlist),
        shortlist[-1].score if shortlist else 0,
        shortlist[0].score if shortlist else 0,
    )
    return shortlist


# ------------------------------------------------- смысловая склейка дублей

MERGE_PROMPT = """Ниже список новостей за сутки. Некоторые описывают одно и то же
событие разными словами — например "Amazon хочет развернуть 5105 спутников" и
"Amazon запускает глобальную спутниковую сеть к 2028" это одна новость.

{items}

Сгруппируй новости по событиям. Верни ТОЛЬКО JSON вида:
{{"groups": [[1], [2, 7, 9], [3], [4, 5]]}}

Каждый id должен встретиться ровно один раз. Объединяй только если это
действительно одно событие. Две разные новости про одну компанию — это
две новости, а не одна."""


def merge_related(items: list[Item]) -> list[Item]:
    """Дособирает дубли, которые не поймала склейка по словам.

    Работает по шортлисту (десятки штук), а не по всему потоку — один дешёвый
    вызов. Ловит случаи вроде "Kimi K3 открытые веса" и "Kimi-K3 Technical
    Report", где общих слов почти нет, но событие одно.
    """
    if len(items) < 2:
        return items

    listing = "\n".join(
        f"{idx}. [{item.source}] {item.title}" for idx, item in enumerate(items, 1)
    )

    try:
        groups = llm.ask_json(
            config.SCORING_MODEL,
            MERGE_PROMPT.format(items=listing),
            max_tokens=2048,
        )
    except Exception as exc:
        log.warning("Смысловая склейка пропущена: %s", exc)
        return items

    result: list[Item] = []
    used: set[int] = set()

    for group in groups:
        if not isinstance(group, list):
            continue
        members = []
        for raw_id in group:
            try:
                idx = int(raw_id) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(items) and idx not in used:
                used.add(idx)
                members.append(items[idx])
        if not members:
            continue

        # Представителем берём новость с большим баллом
        members.sort(key=lambda i: i.score, reverse=True)
        best = members[0]
        for other in members[1:]:
            best.duplicates.append(other)
            best.duplicates.extend(other.duplicates)
        result.append(best)

    # Подстраховка: если модель кого-то потеряла, возвращаем его как есть
    for idx, item in enumerate(items):
        if idx not in used:
            result.append(item)

    result.sort(key=lambda i: i.score, reverse=True)
    if len(result) < len(items):
        log.info("Смысловая склейка: %d -> %d событий", len(items), len(result))
    return result
