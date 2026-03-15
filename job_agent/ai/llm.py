from __future__ import annotations

from job_agent.config import (
    ENABLE_LLM_FALLBACK,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_URL,
)


def ask_llm(prompt: str) -> str | None:
    if not ENABLE_LLM_FALLBACK or not OLLAMA_MODEL:
        return None

    try:
        import requests
    except ImportError:
        return None

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
    except Exception:
        return None

    content = body.get("response")
    if not isinstance(content, str):
        return None

    content = content.strip()
    return content or None
