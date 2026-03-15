from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from job_agent.config import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    ENABLE_TRANSFORMER_EMBEDDINGS,
)


def _normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def _hash_embedding(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    tokens = re.findall(r"[a-z0-9]+", text.lower())

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        direction = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += direction

    return _normalize(vector)


@lru_cache(maxsize=1)
def _load_transformer_model():
    if not ENABLE_TRANSFORMER_EMBEDDINGS:
        return None

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None

    try:
        return SentenceTransformer(EMBEDDING_MODEL)
    except Exception:
        return None


def generate_embedding(text: str | None) -> list[float]:
    safe_text = text or ""
    model = _load_transformer_model()

    if model is None:
        return _hash_embedding(safe_text)

    vector = model.encode(safe_text)
    return vector.tolist()
