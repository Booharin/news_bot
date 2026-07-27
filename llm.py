"""Тонкая обёртка над OpenAI API: один клиент и надёжный разбор JSON."""

from __future__ import annotations

import json
import logging
import os
import re

from openai import OpenAI

log = logging.getLogger(__name__)

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("Не задан OPENAI_API_KEY — проверь файл .env")
        _client = OpenAI(api_key=key)
    return _client


def list_models() -> list[str]:
    """Какие модели доступны твоему ключу. Названия версий меняются часто."""
    return sorted(model.id for model in client().models.list())


def ask(
    model: str,
    prompt: str,
    max_tokens: int = 4096,
    system: str = "",
    json_mode: bool = False,
) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_tokens,
    }
    if json_mode:
        # Гарантирует синтаксически валидный JSON на выходе
        kwargs["response_format"] = {"type": "json_object"}

    response = client().chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def ask_json(model: str, prompt: str, max_tokens: int = 4096, system: str = ""):
    """Как ask, но возвращает разобранный JSON.

    Режим json_object требует объект верхнего уровня, поэтому промпты просят
    обёртку вида {"scores": [...]}. Если пришёл словарь с единственным ключом
    и списком внутри — разворачиваем список.
    """
    raw = ask(
        model, prompt, max_tokens=max_tokens, system=system, json_mode=True
    ).strip()

    data = _loads(raw)

    if isinstance(data, dict) and len(data) == 1:
        only_value = next(iter(data.values()))
        if isinstance(only_value, list):
            return only_value

    return data


def _loads(raw: str):
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"[\[{].*[\]}]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        log.error("Не удалось разобрать JSON из ответа модели: %s", raw[:500])
        raise
