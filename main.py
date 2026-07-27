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
import score
import storage
import summarize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("digest")


def build_digest() -> tuple[list, list]:
    """Возвращает (топ для дайджеста, короткие упоминания)."""
    items = collect.collect_all()
    if not items:
        log.warning("Источники ничего не вернули")
        return [], []

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
        return [], []

    top = shortlist[: config.DIGEST_SIZE]
    extras = shortlist[config.DIGEST_SIZE : config.DIGEST_SIZE + 4]

    top = summarize.write_cards(top)
    return top, extras


def main() -> int:
    parser = argparse.ArgumentParser(description="Утренний дайджест новостей")
    parser.add_argument(
        "--dry-run", action="store_true", help="напечатать вместо отправки"
    )
    parser.add_argument(
        "--collect", action="store_true", help="только сбор, без вызовов модели"
    )
    args = parser.parse_args()

    load_dotenv()

    if args.collect:
        items = dedupe.deduplicate(collect.collect_all())
        for item in items[:60]:
            print(f"[{item.source:18}] {item.title[:90]}")
        print(f"\nВсего событий после дедупликации: {len(items)}")
        return 0

    try:
        top, extras = build_digest()
    except Exception:
        log.exception("Дайджест не собрался")
        return 1

    text = deliver.format_digest(top, extras)

    if args.dry_run:
        print("\n" + text + "\n")
        return 0

    try:
        deliver.send_to_telegram(text)
    except Exception:
        log.exception("Отправка не удалась")
        return 1

    # Помечаем отправленное только после успешной доставки
    pairs = [(i.url, dedupe.normalize_title(i.title)) for i in top]
    for item in top:
        for dup in item.duplicates:
            pairs.append((dup.url, dedupe.normalize_title(dup.title)))
    storage.mark_sent(pairs)
    storage.prune()

    log.info("Готово: %d новостей в выпуске", len(top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
