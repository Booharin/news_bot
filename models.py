"""Общие структуры данных."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Item:
    """Одна новость из источника."""

    title: str
    url: str
    source: str
    published: datetime
    summary: str = ""          # краткое описание из ленты, если есть
    points: int = 0            # очки на HN, для RSS всегда 0

    # Заполняется на следующих этапах пайплайна
    score: float = 0.0
    reason: str = ""           # почему модель поставила такой балл
    is_startup: bool = False   # относится ли к стартапам/новым продуктам/сделкам
    is_indie: bool = False     # инди-разработчик и экономика его продукта
    duplicates: list[Item] = field(default_factory=list)
    article_text: str = ""
    card: str = ""             # готовый текст для дайджеста

    @property
    def all_sources(self) -> list[str]:
        """Источники по этому событию, включая дубли."""
        seen = [self.source]
        for dup in self.duplicates:
            if dup.source not in seen:
                seen.append(dup.source)
        return seen
