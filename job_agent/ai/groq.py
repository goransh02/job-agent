from __future__ import annotations

import json
from typing import Any

from job_agent.config import (
    JOB_AGENT_GROQ_API_KEY,
    JOB_AGENT_GROQ_BASE_URL,
    JOB_AGENT_GROQ_TIMEOUT_SECONDS,
)


def has_groq_configuration() -> bool:
    return bool(JOB_AGENT_GROQ_API_KEY.strip())


def groq_chat_completion(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    response_format: dict[str, str] | None = None,
) -> str | None:
    if not has_groq_configuration() or not model:
        return None

    try:
        import requests
    except ImportError:
        return None

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format

    try:
        response = requests.post(
            JOB_AGENT_GROQ_BASE_URL,
            headers={
                "Authorization": f"Bearer {JOB_AGENT_GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=JOB_AGENT_GROQ_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
    except Exception:
        return None

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        cleaned = content.strip()
        return cleaned or None

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        joined = "\n".join(parts).strip()
        return joined or None

    return None


def groq_json_completion(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
) -> Any:
    content = groq_chat_completion(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    if content is None:
        return None

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None
