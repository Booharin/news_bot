"""Тонкая обёртка над Claude API: один клиент и надёжный разбор JSON."""

from __future__ import annotations

import json
import logging
import os
import re

import anthropic

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("Не задан ANTHROPIC_API_KEY — проверь файл .env")
        _client = anthropic.Anthropic(api_key=key)
    return _client


def ask(model: str, prompt: str, max_tokens: int = 4096, system: str = "") -> str:
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    response = client().messages.create(**kwargs)
    return "".join(block.text for block in response.content if block.type == "text")


def ask_json(model: str, prompt: str, max_tokens: int = 4096, system: str = ""):
    """Как ask, но вытаскивает JSON из ответа.

    Модель иногда оборачивает JSON в ```json ... ``` или добавляет пояснение —
    поэтому не полагаемся на чистый json.loads.
    """
    raw = ask(model, prompt, max_tokens=max_tokens, system=system).strip()

    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Последняя попытка: берём самый внешний массив или объект
        match = re.search(r"[\[{].*[\]}]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        log.error("Не удалось разобрать JSON из ответа модели: %s", raw[:500])
        raise
