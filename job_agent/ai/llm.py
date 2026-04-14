from __future__ import annotations

from job_agent.ai.groq import groq_chat_completion, groq_json_completion
from job_agent.config import (
    ENABLE_LLM_FALLBACK,
    JOB_AGENT_GROQ_REASONING_MODEL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_URL,
)


DEFAULT_SYSTEM_PROMPT = (
    "You are helping fill job application forms. Respond with the most relevant answer only."
)


def ask_llm(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
) -> str | None:
    groq_response = groq_chat_completion(
        model=model or JOB_AGENT_GROQ_REASONING_MODEL,
        system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        temperature=0.0,
    )
    if groq_response:
        return groq_response

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


def ask_llm_json(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
):
    response = groq_json_completion(
        model=model or JOB_AGENT_GROQ_REASONING_MODEL,
        system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        temperature=0.0,
    )
    return response
