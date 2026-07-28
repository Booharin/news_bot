"""Настройки дайджеста: источники, профиль интересов, параметры отбора.

Это единственный файл, который нужно править под себя.
"""

# ---------------------------------------------------------------- окно и объёмы

# Сколько часов назад считать новость свежей
WINDOW_HOURS = 24

# Сколько кандидатов оставить после скоринга (для них тянется полный текст).
# Должно быть заметно больше DIGEST_SIZE: часть кандидатов схлопнется при
# смысловой склейке, часть отвалится, если статью не удалось скачать.
SHORTLIST_SIZE = 45

# Сколько новостей попадёт в итоговый дайджест
DIGEST_SIZE = 20

# Минимальный балл, ниже которого новость не попадёт в дайджест,
# даже если кандидатов не хватает. Лучше короткий выпуск, чем выпуск с мусором.
MIN_SCORE = 6.0

# Модели OpenAI: дешёвая для скоринга сотен заголовков, сильная для текстов.
# Названия версий меняются часто — проверь доступные своему ключу командой
#   python main.py --models
# и поправь, если этих в списке нет.
SCORING_MODEL = "gpt-5.6-luna"
WRITING_MODEL = "gpt-5.6-terra"

# Сколько заголовков отправлять в одном запросе на скоринг
SCORING_BATCH_SIZE = 40

# ------------------------------------------------------------- профиль интересов

# Этот текст подставляется в промпт скоринга. Пиши человеческим языком —
# модель понимает нюансы лучше, чем список ключевых слов.
INTEREST_PROFILE = """
Приоритет 1 — стартапы, новые идеи, бизнес. Самое важное.
  - новые продукты и компании, которых раньше не было; необычные бизнес-модели;
    Show HN, Product Hunt, первые релизы
  - раунды, M&A, смена стратегии или бизнес-модели, резкий рост или провал,
    разворот продукта, уход основателей, закрытия
  - сдвиги в индустрии и появление новых ниш
  Интересны идеи и траектории компаний, а не финансовая отчётность корпораций.

Приоритет 2 — AI и LLM. Релизы моделей (OpenAI, Anthropic, Google, Meta,
  китайские лабы), значимые research-статьи, агенты, инструменты для
  разработки с AI.

Приоритет 3 — технологии и продукты. Любые заметные запуски и железо,
  у любых компаний — от гигантов до незнакомых команд. Apple не выделяется.

Приоритет 4 — разработка. Языки, инфраструктура, инженерные разборы,
  заметные open source проекты.

Не интересно совсем:
  - политика, спорт, знаменитости, криминал — кроме случаев прямого влияния
    на технологический рынок
  - пресс-релизы без сути, listicles вида "10 лучших промптов", SEO-контент,
    слухи без источника
  - минорные обновления версий и косметические апдейты
  - материалы про личную продуктивность и карьерные советы
"""

# ------------------------------------------------------------------- RSS-ленты

RSS_FEEDS = [
    # Общие технологические СМИ
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("Wired", "https://www.wired.com/feed/rss"),
    ("Engadget", "https://www.engadget.com/rss.xml"),

    # Стартапы, венчур, бизнес
    ("Crunchbase News", "https://news.crunchbase.com/feed/"),
    ("Tech Startups", "https://techstartups.com/feed/"),
    ("Sifted", "https://sifted.eu/feed"),
    ("VentureBeat", "https://venturebeat.com/feed/"),
    ("Stratechery", "https://stratechery.com/feed/"),

    # AI
    ("OpenAI", "https://openai.com/news/rss.xml"),
    # У Anthropic официального RSS нет. Это неофициальное зеркало от сообщества:
    # может сломаться в любой момент, тогда просто удали строку — релизы
    # Anthropic всё равно попадают в TechCrunch и на Hacker News.
    ("Anthropic", "https://tim-hilde.github.io/anthropic-rss/rss.xml"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    ("Google Research", "https://research.google/blog/rss/"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
    ("MIT Tech Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    # Import AI и The Batch убраны: первый режется Substack по серверным IP,
    # второй отдаёт 500. Покрытие AI-новостей и так избыточное.

    # Инженерные блоги
    ("GitHub Blog", "https://github.blog/feed/"),
    ("Cloudflare Blog", "https://blog.cloudflare.com/rss/"),
    ("Stripe Blog", "https://stripe.com/blog/feed.rss"),
    ("Vercel Blog", "https://vercel.com/atom"),
    ("Netflix Tech", "https://netflixtechblog.com/feed"),
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
]

# --------------------------------------------------------------- Hacker News

# Минимум очков, чтобы история с HN попала в кандидаты.
# Show HN отбирается отдельно и с более низким порогом — там важна новизна,
# а не популярность.
HN_MIN_POINTS = 80
HN_SHOW_MIN_POINTS = 15

# Сколько историй запрашивать максимум
HN_MAX_STORIES = 120

# ------------------------------------------------------------------ прочее

# Домены, которые никогда не попадают в дайджест (агрегаторы, контент-фермы)
BLOCKED_DOMAINS = {
    "medium.com",
    "dev.to",
    "hackernoon.com",
    # Соцсети: текст оттуда не вытащить, а карточка выходит пустой
    "twitter.com",
    "x.com",
    "threads.net",
    "reddit.com",
    # Жёсткий paywall — статью скачать не получится
    "bloomberg.com",
    "wsj.com",
    "ft.com",
}

# Мусорные заголовки: гайды, подборки и распродажи, которые издания
# публикуют потоком. Отсекаются до скоринга — не тратим на них токены.
JUNK_TITLE_PATTERNS = [
    r"^(the )?best .{0,60}\b(for |of |in )?20\d\d",   # Best wireless headphones for 2026
    r"^how to\b",                                      # How to Clear The Cache On Your Roku TV
    r"^what('s| is| are)\b.{0,40}\bdifference\b",      # What's the difference between USB 3.0 & 2.0
    r"\bis half off\b|\b\d{1,2}% off\b|\bdeal of the day\b",
    r"^\d{1,2} (best|things|ways|tips)\b",
    r"\bhere's how\b.{0,30}\bfix\b",                   # Here's how to fix it
    r"^(everything|all) you need to know\b",
]

# Таймаут на сетевые запросы, секунды
HTTP_TIMEOUT = 20

# Часть изданий (в частности Substack) отдаёт 403 роботам с честным
# User-Agent. Представляемся браузером — иначе теряем живые ленты.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
