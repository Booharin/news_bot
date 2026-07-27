"""Офлайн-проверка логики, которая не требует сети и ключей API.

Запуск: python test_offline.py
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import dedupe
import deliver
import storage
from models import Item


def item(title: str, url: str, source: str, points: int = 0) -> Item:
    return Item(
        title=title,
        url=url,
        source=source,
        published=datetime.now(timezone.utc),
        points=points,
    )


def test_normalize_strips_publisher() -> None:
    assert dedupe.normalize_title("OpenAI ships GPT-6 | TechCrunch") == "openai ships gpt 6"
    assert dedupe.normalize_title("Stripe buys Foo - The Verge") == "stripe buys foo"


def test_canonical_url_drops_tracking() -> None:
    a = dedupe.canonical_url("https://www.example.com/post/?utm_source=rss#top")
    b = dedupe.canonical_url("http://example.com/post")
    assert a == b == "https://example.com/post"


def test_dedupe_merges_same_event() -> None:
    items = [
        item("Anthropic releases Claude Opus 5", "https://a.com/1", "TechCrunch"),
        item("Anthropic has released Claude Opus 5 model", "https://b.com/2", "The Verge"),
        item("Claude Opus 5 released by Anthropic", "https://anthropic.com/news", "Anthropic"),
        item("Rocket Lab to acquire Iridium for $8B", "https://c.com/3", "Ars Technica"),
    ]
    result = dedupe.deduplicate(items)

    assert len(result) == 2, f"ожидалось 2 события, вышло {len(result)}"
    # Представителем кластера должен стать первоисточник, а не пересказ
    cluster = [r for r in result if "Opus" in r.title][0]
    assert cluster.source == "Anthropic", f"выбран {cluster.source}"
    assert len(cluster.duplicates) == 2
    assert "TechCrunch" in cluster.all_sources


def test_dedupe_keeps_different_events_apart() -> None:
    items = [
        item("Etched raises $300M Series C", "https://a.com/1", "TechCrunch"),
        item("Neo raises $100M for AI security", "https://b.com/2", "TechCrunch"),
    ]
    assert len(dedupe.deduplicate(items)) == 2


def test_format_escapes_html() -> None:
    news = item("Test", "https://example.com/a&b", "TechCrunch")
    news.card = {
        "headline": "Компания <Foo> купила Bar",
        "what": "Сделка на $1 млрд & опционы.",
        "why": "",
    }
    text = deliver.format_digest([news])

    assert "&lt;Foo&gt;" in text, "угловые скобки не экранированы"
    assert "&amp;" in text, "амперсанд не экранирован"
    assert "Почему важно" not in text, "пустое why не должно печататься"
    assert "<b>1." in text


def test_format_empty_digest() -> None:
    text = deliver.format_digest([])
    assert "нечего показать" in text


def test_split_respects_limit() -> None:
    block = "x" * 1000
    long_text = "\n\n".join([block] * 8)
    chunks = deliver._split(long_text)

    assert len(chunks) > 1
    assert all(len(c) <= deliver.MAX_MESSAGE for c in chunks)


def test_storage_roundtrip() -> None:
    # Пишем во временный файл, чтобы не трогать боевую базу
    storage.DB_PATH = Path(tempfile.gettempdir()) / "digest_test.db"
    storage.DB_PATH.unlink(missing_ok=True)
    try:
        assert storage.already_sent(["https://a.com/1"], ["foo bar"]) == set()

        storage.mark_sent([("https://a.com/1", "foo bar")])
        assert storage.already_sent(["https://a.com/1"], ["foo bar"]) == {"https://a.com/1"}

        # Та же новость под другой ссылкой должна отсечься по заголовку
        seen = storage.already_sent(["https://other.com/2"], ["foo bar"])
        assert seen == {"https://other.com/2"}, "дубль по заголовку не пойман"

        assert storage.already_sent(["https://c.com/3"], ["другая новость"]) == set()
    finally:
        storage.DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"OK    {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {test.__name__}: {exc}")
        except Exception as exc:
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")

    print(f"\n{len(tests) - failed}/{len(tests)} прошло")
    raise SystemExit(1 if failed else 0)
