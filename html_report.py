"""Сборка HTML-версии дайджеста — той самой, что уходит файлом в Telegram."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from models import Item

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

CSS = """
:root {
  --bg:#faf9f7; --ink:#1c1a17; --muted:#6b6660; --line:#e6e2dc;
  --accent:#b4552d; --accent2:#2f6f5e; --accent3:#6a4c93; --why-bg:#f5f2ec;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg:#161513; --ink:#eae7e1; --muted:#9a948b; --line:#302e2a;
    --accent:#e0885c; --accent2:#6fb6a0; --accent3:#b39ddb; --why-bg:#26241f;
  }
}
*{box-sizing:border-box}
body{margin:0;padding:0 20px 80px;background:var(--bg);color:var(--ink);
  font:17px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:720px;margin:0 auto}
header{padding:56px 0 28px;border-bottom:2px solid var(--ink)}
h1{margin:0;font-size:40px;line-height:1.1;letter-spacing:-.02em;font-weight:700}
.sub{margin-top:10px;color:var(--muted);font-size:15px}
.section{margin:44px 0 4px;font-size:13px;font-weight:700;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);padding-bottom:10px;
  border-bottom:1px solid var(--line)}
.section.startups{color:var(--accent2)}
.section.indie{color:var(--accent3)}
article{padding:28px 0;border-bottom:1px solid var(--line)}
.num{display:inline-block;font-size:13px;font-weight:700;letter-spacing:.08em;
  color:var(--accent);margin-bottom:6px}
.startups-block .num{color:var(--accent2)}
.indie-block .num{color:var(--accent3)}
h2{margin:0 0 12px;font-size:21px;line-height:1.32;letter-spacing:-.01em;font-weight:650}
p{margin:0 0 14px}
.why{background:var(--why-bg);border-left:3px solid var(--accent);padding:12px 16px;
  margin:0 0 14px;border-radius:0 6px 6px 0;font-size:16px}
.startups-block .why{border-left-color:var(--accent2)}
.indie-block .why{border-left-color:var(--accent3)}
.why b{font-weight:650}
.src a{color:var(--muted);font-size:14px;text-decoration:none;
  border-bottom:1px solid var(--line);padding-bottom:1px}
.src a:hover{color:var(--accent);border-color:var(--accent)}
footer{padding-top:32px;color:var(--muted);font-size:14px}
@media (max-width:600px){
  header{padding-top:36px} h1{font-size:30px} h2{font-size:19px} body{font-size:16px}
}
"""


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _plural(count: int, one: str, few: str, many: str) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def _article(item: Item, num: int) -> str:
    card = item.card
    parts = [
        "<article>",
        f'  <div class="num">{num:02d}</div>',
        f"  <h2>{_esc(card['headline'])}</h2>",
    ]
    if card["what"]:
        parts.append(f"  <p>{_esc(card['what'])}</p>")
    if card["why"]:
        parts.append(
            f'  <p class="why"><b>Почему важно:</b> {_esc(card["why"])}</p>'
        )

    sources = ", ".join(item.all_sources[:3])
    parts.append(
        f'  <div class="src"><a href="{html.escape(item.url)}">{_esc(sources)}</a></div>'
    )
    parts.append("</article>")
    return "\n".join(parts)


def render(
    items: list[Item],
    startups: list[Item],
    extras: list[Item] | None = None,
    indie: list[Item] | None = None,
) -> str:
    indie = indie or []
    today = datetime.now()
    date_str = f"{today.day} {MONTHS[today.month - 1]}"
    total = len(items) + len(startups) + len(indie)

    body = [
        "<header>",
        f"  <h1>Дайджест за {date_str}</h1>",
        f'  <div class="sub">{total} '
        f"{_plural(total, 'материал', 'материала', 'материалов')} · "
        f"{len(items)} в главном, {len(startups)} про стартапы, "
        f"{len(indie)} про инди</div>",
        "</header>",
    ]

    number = 1

    if items:
        body.append('<div class="section">Главное</div>')
        body.extend(_article(item, n) for n, item in enumerate(items, number))
        number += len(items)

    if startups:
        body.append('<div class="section startups">Стартапы и новые идеи</div>')
        body.append('<div class="startups-block">')
        body.extend(_article(item, n) for n, item in enumerate(startups, number))
        body.append("</div>")
        number += len(startups)

    if indie:
        body.append('<div class="section indie">Инди и заработок на продуктах</div>')
        body.append('<div class="indie-block">')
        body.extend(_article(item, n) for n, item in enumerate(indie, number))
        body.append("</div>")
        number += len(indie)

    footer = []
    if extras:
        titles = "; ".join(_esc(i.title) for i in extras[:4])
        footer.append(f"Ещё мельком: {titles}<br><br>")
    footer.append(
        f"Собрано автоматически из RSS и Hacker News · {date_str} {today.year}"
    )
    body.append("<footer>" + "\n".join(footer) + "</footer>")

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Дайджест за {date_str}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{chr(10).join(body)}
</div>
</body>
</html>
"""


def save(
    items: list[Item],
    startups: list[Item],
    extras: list[Item] | None = None,
    indie: list[Item] | None = None,
    directory: Path | None = None,
) -> Path:
    """Пишет HTML на диск и возвращает путь. Имя с датой — архив сам собой."""
    directory = directory or Path(__file__).parent / "archive"
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / f"digest-{datetime.now():%Y-%m-%d}.html"
    path.write_text(render(items, startups, extras, indie), encoding="utf-8")
    return path
