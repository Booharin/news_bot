"""Офлайн-проверка логики, которая не требует сети и ключей API.

Запуск: python test_offline.py
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import collect
import dedupe
import deliver
import storage
from models import Item  # noqa: F401  (используется в хелперах ниже)


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


def test_junk_filter_catches_listicles() -> None:
    junk = [
        "Best wireless headphones for 2026",
        "How to Clear The Cache On Your Roku TV",
        "What's the difference between USB 3.0 and 2.0?",
        "Nanoleaf's colorful pegboard and shelf kit is half off",
        "Everything you need to know about the Pixel 11",
    ]
    for title in junk:
        assert collect._is_junk(title), f"не отсеклось: {title}"


def test_junk_filter_keeps_real_news() -> None:
    real = [
        "Antares raises $470M to build nuclear reactors for the US military",
        "Moonshot AI releases Kimi K3 open weights",
        "Google Pixel 11 launch event: Everything we expect as price rumors grow",
        "Framework Laptop 13 Pro review: Much better battery, much worse price",
    ]
    for title in real:
        assert not collect._is_junk(title), f"ложное срабатывание: {title}"


def _scored(title: str, score_value: float, startup: bool) -> Item:
    news = item(title, f"https://x.com/{title}", "TechCrunch")
    news.score = score_value
    news.is_startup = startup
    return news


def test_sections_do_not_overlap() -> None:
    """Раздел про стартапы добавляет новости, а не повторяет главное."""
    import score

    items = [_scored(f"big{i}", 9.0, False) for i in range(5)]
    items += [_scored(f"su{i}", 8.0, True) for i in range(10)]

    main, startups = score.split_digest(items, main_size=10, startup_size=10)

    assert len(main) == 10
    main_urls = {i.url for i in main}
    assert all(i.url not in main_urls for i in startups), "раздел дублирует главное"
    # 5 стартапов попали в главное, ещё 5 остались на второй раздел
    assert len(startups) == 5
    assert all(i.is_startup for i in startups)


def test_startup_section_empty_when_no_startups() -> None:
    import score

    items = [_scored(f"big{i}", 9.0, False) for i in range(10)]
    main, startups = score.split_digest(items, main_size=5, startup_size=10)

    assert len(main) == 5
    assert startups == []


def test_html_report_renders_both_sections() -> None:
    import html_report

    news = item("a", "https://example.com/a", "TechCrunch")
    news.card = {"headline": "Главное <тут>", "what": "Текст & детали.", "why": "Важно."}
    su = item("b", "https://example.com/b", "Show HN")
    su.card = {"headline": "Стартап", "what": "Текст.", "why": ""}

    page = html_report.render([news], [su])

    assert page.startswith("<!DOCTYPE html>")
    assert "Главное &lt;тут&gt;" in page, "угловые скобки не экранированы"
    assert "Текст &amp; детали." in page
    assert 'class="section startups"' in page
    # Нумерация сквозная и двузначная
    assert '<div class="num">01</div>' in page
    assert '<div class="num">02</div>' in page
    # Пустое why не рендерится
    assert page.count('class="why"') == 1


def test_telegram_number_is_a_link() -> None:
    """Цвет в Telegram даёт только ссылка, поэтому номер кликабельный."""
    news = item("a", "https://example.com/a", "TechCrunch")
    news.card = {"headline": "Заголовок", "what": "Текст.", "why": "Важно."}

    text = deliver.format_digest([news])

    assert '<a href="https://example.com/a">01</a>' in text
    assert "<blockquote>Почему важно: Важно.</blockquote>" in text


def test_format_survives_missing_sections() -> None:
    """В пустой день разделов может не быть — сборка не должна падать."""
    assert "нечего показать" in deliver.format_digest([], None, None)
    assert "нечего показать" in deliver.format_digest([], [], [])

    su = item("b", "https://example.com/b", "Show HN")
    su.card = {"headline": "Только стартап", "what": "Текст.", "why": ""}
    text = deliver.format_digest([], None, [su])
    assert "СТАРТАПЫ" in text
    assert "ГЛАВНОЕ" not in text


def test_format_renders_two_sections() -> None:
    news = item("a", "https://example.com/a", "TechCrunch")
    news.card = {"headline": "Главная новость", "what": "Текст.", "why": ""}
    su = item("b", "https://example.com/b", "Show HN")
    su.card = {"headline": "Новый стартап", "what": "Текст.", "why": ""}

    text = deliver.format_digest([news], None, [su])

    assert "ГЛАВНОЕ" in text
    assert "СТАРТАПЫ И НОВЫЕ ИДЕИ" in text
    # Нумерация сквозная: второй раздел продолжает первый
    assert "<b>Главная новость</b>" in text
    assert '<a href="https://example.com/b">02</a>' in text


def test_blocked_domains_cover_subdomains() -> None:
    assert collect._is_blocked("https://twitter.com/a/status/1")
    assert collect._is_blocked("https://www.bloomberg.com/news/a")
    assert collect._is_blocked("https://old.reddit.com/r/startups")
    assert not collect._is_blocked("https://techcrunch.com/2026/07/28/x")
    # Не должно ловить домены, лишь заканчивающиеся так же
    assert not collect._is_blocked("https://notreddit.com/a")


def test_clean_decodes_entities() -> None:
    # Ленты отдают мнемоники, в дайджест они попадать не должны
    assert "’" in collect._clean("Nanoleaf&#8217;s kit")
    assert "&#" not in collect._clean("Amazon&#8217;s network")


def test_dedupe_merges_near_duplicate_headlines() -> None:
    # Реальная пара, которую прежний порог 0.6 пропускал
    items = [
        item("YouTube Premium will soon include Peacock at no extra cost",
             "https://a.com/1", "Engadget"),
        item("YouTube Premium will include Peacock starting next year",
             "https://b.com/2", "The Verge"),
    ]
    assert len(dedupe.deduplicate(items)) == 1


def test_ask_json_unwraps_object_wrapper() -> None:
    """Режим json_object у OpenAI не умеет отдавать массив верхнего уровня,
    поэтому промпты просят обёртку. Проверяем, что она разворачивается."""
    import llm

    original = llm.ask
    try:
        llm.ask = lambda *a, **kw: '{"scores": [{"id": 1, "score": 7}]}'
        assert llm.ask_json("m", "p") == [{"id": 1, "score": 7}]

        llm.ask = lambda *a, **kw: '{"groups": [[1], [2, 3]]}'
        assert llm.ask_json("m", "p") == [[1], [2, 3]]

        # Карточка новости — обычный объект, разворачивать нечего
        llm.ask = lambda *a, **kw: '{"headline": "h", "what": "w", "why": ""}'
        assert llm.ask_json("m", "p")["headline"] == "h"
    finally:
        llm.ask = original


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
    assert "<b>Компания &lt;Foo&gt; купила Bar</b>" in text


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
