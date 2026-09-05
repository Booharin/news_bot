"""Настройки дайджеста: источники, профиль интересов, параметры отбора.

Это единственный файл, который нужно править под себя.
"""

# ---------------------------------------------------------------- окно и объёмы

# Сколько часов назад считать новость свежей
WINDOW_HOURS = 24

# Сколько кандидатов оставить после скоринга (для них тянется полный текст).
# Должно быть заметно больше суммы разделов: часть кандидатов схлопнется при
# смысловой склейке, часть отвалится, если статью не удалось скачать.
SHORTLIST_SIZE = 80

# Первый раздел, «Главное» — лучшие новости по баллу, тема любая
DIGEST_SIZE = 20

# Второй раздел, «Стартапы и новые идеи» — только про новые компании, продукты,
# раунды и сделки. Собирается из того, что не попало в первый раздел, поэтому
# добавляет объём, а не переставляет местами уже отобранное.
STARTUP_SECTION_SIZE = 20

# Третий раздел, «Инди и заработок на продуктах» — одиночные разработчики
# и маленькие команды в любом формате: приложения, веб-сервисы, боты,
# расширения. Выручка, MRR, истории запусков без инвестиций.
# Тоже собирается из остатка и ничего не дублирует.
INDIE_SECTION_SIZE = 10

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

Приоритет 4 — инди-разработка и заработок на своих продуктах. Одиночные
  разработчики и маленькие команды, любой формат продукта: мобильные
  приложения, веб-сервисы и SaaS, телеграм- и дискорд-боты, расширения для
  браузера, десктопные утилиты, API и инструменты для разработчиков,
  платные шаблоны и плагины.
  Что интересно: сколько продукт зарабатывает, выручка и MRR, доходы в App
  Store и других сторах, истории запусков без инвестиций, разборы монетизации
  и подписок, отчёты о доходах, как искали первых платящих пользователей.
  Ценны конкретные цифры и честные разборы, включая провалы и закрытия.
  Мотивационные истории без деталей неинтересны.

Приоритет 5 — разработка. Языки, инфраструктура, инженерные разборы,
  заметные open source проекты.

Не интересно совсем:
  - политика, спорт, знаменитости, криминал — кроме случаев прямого влияния
    на технологический рынок
  - пресс-релизы без сути, listicles вида "10 лучших промптов", SEO-контент,
    слухи без источника
  - минорные обновления версий и косметические апдейты
  - материалы про личную продуктивность и карьерные советы
  - «как заработать в интернете», курсы, инфобизнес и мотивационные посты
    без конкретных цифр и деталей
"""

# ------------------------------------------------------------------- RSS-ленты

RSS_FEEDS = [
    # Общие технологические СМИ
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("Wired", "https://www.wired.com/feed/rss"),
    ("Engadget", "https://www.engadget.com/rss.xml"),

    # Стартапы, венчур, бизнес — главный приоритет, поэтому источников больше
    ("Crunchbase News", "https://news.crunchbase.com/feed/"),
    ("Tech Startups", "https://techstartups.com/feed/"),
    ("Sifted", "https://sifted.eu/feed"),
    ("VentureBeat", "https://venturebeat.com/feed/"),
    ("Stratechery", "https://stratechery.com/feed/"),
    ("TechCrunch Startups", "https://techcrunch.com/category/startups/feed/"),
    ("TechCrunch Venture", "https://techcrunch.com/category/venture/feed/"),
    ("EU-Startups", "https://www.eu-startups.com/feed/"),
    ("Tech.eu", "https://tech.eu/feed/"),
    # Product Hunt убран: лента отдаётся, но сами страницы товаров закрыты
    # от ботов (403), текст не вытащить и карточка не пишется — только
    # впустую тратились токены на скоринг.
    ("Y Combinator Blog", "https://www.ycombinator.com/blog/rss"),
    ("TechCrunch Fintech", "https://techcrunch.com/category/fintech/feed/"),

    # Инди-разработка и экономика небольших продуктов. Потока не дают —
    # пишут раз в неделю-две, — но материалы по теме редкие и качественные.
    # Если какая-то лента отдаст 404, просто удали строку.
    ("Bootstrapped Founder", "https://thebootstrappedfounder.com/feed/"),
    ("Indie Hackers", "https://www.indiehackers.com/feed.xml"),
    ("RevenueCat Blog", "https://www.revenuecat.com/blog/rss.xml"),
    ("Appfigures Blog", "https://appfigures.com/resources/feed"),

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
# Show HN — это витрина новых проектов, ровно то, что нужно. Порог низкий:
# хороший проект может собрать мало очков просто потому, что попал в неудачное
# время суток, а нам важна новизна, а не популярность.
HN_SHOW_MIN_POINTS = 8

# Сколько историй запрашивать максимум
HN_MAX_STORIES = 120

# Поиск по ключевым словам — основной канал для инди-темы.
# Обычные техномедиа про доходы одиночных разработчиков не пишут вообще,
# зато на HN это регулярный жанр. Порог очков низкий: такие посты интересны
# узкой аудитории и сотню апвоутов набирают редко.
HN_KEYWORD_QUERIES = [
    "MRR",
    "bootstrapped",
    "solo founder",
    "indie hacker",
    "micro SaaS",
    "App Store revenue",
    "side project revenue",
    "profitable SaaS",
    "revenue report",
    "first paying customers",
]
HN_KEYWORD_MIN_POINTS = 4
HN_KEYWORD_HITS = 30

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
