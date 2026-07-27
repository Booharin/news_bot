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

Верни ТОЛЬКО JSON-массив без пояснений, по объекту на каждую новость:
[{{"id": 1, "score": 7, "reason": "краткое обоснование, до 10 слов"}}]

Обязательно верни объект для каждого id из списка."""


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
