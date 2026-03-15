from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


MONGO_URI = os.getenv("JOB_AGENT_MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("JOB_AGENT_DATABASE_NAME", "job_agent")
MONGO_SERVER_SELECTION_TIMEOUT_MS = _env_int(
    "JOB_AGENT_MONGO_SERVER_SELECTION_TIMEOUT_MS",
    500,
)

DEFAULT_EMAIL = os.getenv("JOB_AGENT_DEFAULT_EMAIL", "")
DEFAULT_PASSWORD = os.getenv("JOB_AGENT_DEFAULT_PASSWORD", "")

SIMILARITY_THRESHOLD = _env_float("JOB_AGENT_SIMILARITY_THRESHOLD", 0.8)
ENABLE_SEMANTIC_SEARCH = _env_bool("JOB_AGENT_ENABLE_SEMANTIC_SEARCH", True)

ENABLE_TRANSFORMER_EMBEDDINGS = _env_bool(
    "JOB_AGENT_ENABLE_TRANSFORMER_EMBEDDINGS",
    False,
)
EMBEDDING_MODEL = os.getenv(
    "JOB_AGENT_EMBEDDING_MODEL",
    "all-MiniLM-L6-v2",
)
EMBEDDING_DIMENSIONS = _env_int("JOB_AGENT_EMBEDDING_DIMENSIONS", 128)

ENABLE_LLM_FALLBACK = _env_bool("JOB_AGENT_ENABLE_LLM_FALLBACK", False)
OLLAMA_URL = os.getenv(
    "JOB_AGENT_OLLAMA_URL",
    "http://127.0.0.1:11434/api/generate",
)
OLLAMA_MODEL = os.getenv("JOB_AGENT_OLLAMA_MODEL", "")
OLLAMA_TIMEOUT_SECONDS = _env_int("JOB_AGENT_OLLAMA_TIMEOUT_SECONDS", 10)

BROWSER_HEADLESS = _env_bool("JOB_AGENT_BROWSER_HEADLESS", True)
BROWSER_SLOW_MO_MS = _env_int("JOB_AGENT_BROWSER_SLOW_MO_MS", 0)
BROWSER_TIMEOUT_MS = _env_int("JOB_AGENT_BROWSER_TIMEOUT_MS", 20000)

AUTO_SUBMIT = _env_bool("JOB_AGENT_AUTO_SUBMIT", False)
