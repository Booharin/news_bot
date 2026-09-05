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

Дополнительно для каждой новости укажи поле startup — true, если речь о
молодой или частной компании: запуск, выход из стелса, раунд финансирования,
поглощение, IPO, смена бизнес-модели, резкий рост или закрытие, а также
новые проекты и продукты небольших команд и отдельных разработчиков.

Для крупных публичных корпораций — Google, Apple, Microsoft, Samsung, Amazon,
Meta, Nvidia, OpenAI, Anthropic и подобных — ставь false ВСЕГДА, даже если они
что-то запускают. Их продуктовые анонсы это не новости про стартапы.
Исключение одно: если корпорация покупает или инвестирует в стартап, тогда true.

Ещё укажи поле indie. Ставь true ТОЛЬКО если выполнены оба условия сразу:

1. Это одиночный разработчик или крошечная команда. Формат продукта любой:
   приложение, веб-сервис, SaaS, телеграм-бот, расширение браузера, утилита,
   API, платный плагин.
2. В новости есть КОНКРЕТНЫЕ ДЕНЬГИ: выручка, MRR, ARR, прибыль, сумма продаж,
   доход в App Store, число платящих пользователей, разбор монетизации с
   цифрами, отчёт о доходах, причины провала с финансовой стороны.

Второе условие обязательно. «Сделал сервис, посмотрите» без единой цифры —
это false, даже если автор одиночка: такие новости идут в startup.
Одна лишь цена подписки без данных о выручке или числе покупателей — тоже
недостаточно.

Раздел про то, сколько продукт зарабатывает, а не про то, что его сделал
один человек.

Мотивационные посты, курсы и «как заработать в интернете» — false и низкий балл.

Для крупных и публичных компаний — UiPath, Spotify, Atlassian, Stripe и любых
других известных — ставь false ВСЕГДА. Их open-source проекты и инструменты
к заработку одиночек отношения не имеют, даже если продукт бесплатный.
Раздел про людей, которые живут с выручки своего маленького продукта.

Если подходят оба поля, ставь true обоим — раздел выберется автоматически.

Верни ТОЛЬКО JSON вида:
{{"scores": [{{"id": 1, "score": 7, "startup": true, "indie": false,
"reason": "до 10 слов"}}]}}

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
            # Потолок с запасом: модели тратят часть бюджета на рассуждения,
            # при тесном лимите ответ приходит обрезанным
            result = llm.ask_json(
                config.SCORING_MODEL, prompt, max_tokens=8192, system=SYSTEM
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
            item.is_startup = bool(entry.get("startup", False))
            item.is_indie = bool(entry.get("indie", False))

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


# ------------------------------------------------------- отбор с квотой

def split_digest(
    items: list[Item], main_size: int, startup_size: int, indie_size: int = 0
) -> tuple[list[Item], list[Item], list[Item]]:
    """Делит отобранное на три непересекающихся раздела по теме.

    «Главное» — всё остальное: AI, разработка, крупные компании.
    «Стартапы и новые идеи» — молодые и частные компании.
    «Инди и заработок на продуктах» — одиночки и экономика их продуктов.

    Деление именно по теме, а не по баллу. Сначала было по баллу, и это
    давало обратный результат: сильные инди-истории вроде «сервис вышел на
    $5,6 тыс. в месяц» набирали высокий балл и оседали в «Главном», а в
    тематические разделы попадали объедки — виртуальный аквариум вместо
    разбора выручки.

    Инди разбирается раньше стартапов: тема у́же, и при совпадении признаков
    новость должна попасть именно туда.
    """
    ranked = sorted(items, key=lambda i: i.score, reverse=True)

    indie = [i for i in ranked if i.is_indie][:indie_size]
    chosen = {i.url for i in indie}

    startups = [i for i in ranked if i.is_startup and i.url not in chosen]
    startups = startups[:startup_size]
    chosen.update(i.url for i in startups)

    main = [i for i in ranked if i.url not in chosen][:main_size]

    log.info(
        "Разделы: главное %d, стартапы %d, инди %d",
        len(main),
        len(startups),
        len(indie),
    )
    return main, startups, indie


# ------------------------------------------------- смысловая склейка дублей

MERGE_PROMPT = """Ниже список новостей за сутки. Некоторые описывают одно и то же
событие разными словами — например "Amazon хочет развернуть 5105 спутников" и
"Amazon запускает глобальную спутниковую сеть к 2028" это одна новость.

{items}

Объединяй в одну группу также разбор и новость об одном и том же: заметка
"Компания X выпустила модель Y" и аналитическая статья "Что означает выход
модели Y" — это одна тема, читателю не нужны оба пункта.

Сгруппируй новости по темам. Верни ТОЛЬКО JSON вида:
{{"groups": [[1], [2, 7, 9], [3], [4, 5]]}}

Каждый id должен встретиться ровно один раз. Две разные новости про одну
компанию — это две новости, а не одна: раунд финансирования и запуск
продукта не объединяй."""


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
            max_tokens=4096,
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
