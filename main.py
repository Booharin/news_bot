"""Точка входа: собрать, отфильтровать, написать, отправить.

Запуск:
    python main.py              — собрать и отправить в Telegram
    python main.py --dry-run    — то же, но напечатать в консоль вместо отправки
    python main.py --collect    — только показать, что нашлось (без вызовов API)
"""

from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

import collect
import config
import dedupe
import deliver
import html_report
import score
import storage
import summarize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)

# httpx логирует полный URL каждого запроса — в случае Telegram это означает
# токен бота открытым текстом в journalctl. Оставляем только предупреждения:
# заодно лог становится читаемым, там и так видно, какие ленты отвалились.
logging.getLogger("httpx").setLevel(logging.WARNING)

log = logging.getLogger("digest")


def build_digest() -> tuple[list, list, list]:
    """Возвращает (главное, стартапы, короткие упоминания)."""
    items = collect.collect_all()
    if not items:
        log.warning("Источники ничего не вернули")
        return [], [], []

    items = dedupe.deduplicate(items)

    # Отсекаем то, что уже уходило в прошлые дни
    urls = [i.url for i in items]
    titles = [dedupe.normalize_title(i.title) for i in items]
    seen = storage.already_sent(urls, titles)
    if seen:
        items = [i for i in items if i.url not in seen]
        log.info("Отброшено как уже отправленное: %d", len(seen))

    shortlist = score.score_items(items)
    if not shortlist:
        return [], [], []

    # Второй проход по дублям: склейка по словам не ловит статьи об одном
    # событии с непохожими заголовками
    shortlist = score.merge_related(shortlist)

    top, startups = score.split_digest(
        shortlist, config.DIGEST_SIZE, config.STARTUP_SECTION_SIZE
    )

    chosen = {i.url for i in top} | {i.url for i in startups}
    extras = [i for i in shortlist if i.url not in chosen][:4]

    # Карточки для обоих разделов одним заходом — так параллелизм эффективнее
    written = summarize.write_cards(top + startups)
    written_urls = {i.url for i in written}
    top = [i for i in top if i.url in written_urls]
    startups = [i for i in startups if i.url in written_urls]

    summarize.translate_titles(extras)
    return top, startups, extras


def main() -> int:
    parser = argparse.ArgumentParser(description="Утренний дайджест новостей")
    parser.add_argument(
        "--dry-run", action="store_true", help="напечатать вместо отправки"
    )
    parser.add_argument(
        "--collect", action="store_true", help="только сбор, без вызовов модели"
    )
    parser.add_argument(
        "--models", action="store_true", help="показать модели, доступные ключу"
    )
    args = parser.parse_args()

    load_dotenv()

    if args.models:
        import llm

        for name in llm.list_models():
            print(name)
        return 0

    if args.collect:
        items = dedupe.deduplicate(collect.collect_all())
        for item in items[:60]:
            print(f"[{item.source:18}] {item.title[:90]}")
        print(f"\nВсего событий после дедупликации: {len(items)}")
        return 0

    try:
        top, startups, extras = build_digest()
    except Exception:
        log.exception("Дайджест не собрался")
        return 1

    text = deliver.format_digest(top, extras, startups)

    if args.dry_run:
        print("\n" + text + "\n")
        if top or startups:
            path = html_report.save(top, startups, extras)
            log.info("HTML-версия сохранена: %s", path)
        return 0

    try:
        deliver.send_to_telegram(text)
    except Exception:
        log.exception("Отправка не удалась")
        return 1

    # Файл — приятное дополнение, его неудача не должна ломать прогон
    if top or startups:
        path = html_report.save(top, startups, extras)
        deliver.send_file(path, caption="Та же подборка в читаемом виде")

    # Помечаем отправленное только после успешной доставки
    sent = top + startups
    pairs = [(i.url, dedupe.normalize_title(i.title)) for i in sent]
    for item in sent:
        for dup in item.duplicates:
            pairs.append((dup.url, dedupe.normalize_title(dup.title)))
    storage.mark_sent(pairs)
    storage.prune()

    log.info(
        "Готово: %d в главном, %d про стартапы", len(top), len(startups)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
