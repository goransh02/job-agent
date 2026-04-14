from __future__ import annotations

import math

from job_agent.ai.embeddings import generate_embedding
from job_agent.config import ENABLE_SEMANTIC_SEARCH, SIMILARITY_THRESHOLD
from job_agent.database.mongo import answers_collection
from job_agent.services.profile_service import normalize_profile_id


def cosine_similarity(vector_a, vector_b) -> float:
    if not vector_a or not vector_b or len(vector_a) != len(vector_b):
        return 0.0

    dot_product = sum(left * right for left, right in zip(vector_a, vector_b))
    norm_a = math.sqrt(sum(value * value for value in vector_a))
    norm_b = math.sqrt(sum(value * value for value in vector_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def search_similar(question: str | None, profile_id: str | None = None) -> str | None:
    if not ENABLE_SEMANTIC_SEARCH or not question:
        return None

    query_vector = generate_embedding(question)
    best_score = 0.0
    best_answer = None
    normalized_profile_id = normalize_profile_id(profile_id)

    try:
        documents = answers_collection.find()
    except Exception:
        return None

    for document in documents:
        document_profile_id = normalize_profile_id(document.get("profile_id"))
        if document_profile_id != normalized_profile_id:
            continue

        embedding = document.get("embedding")
        answer = document.get("answer")
        if not embedding or not answer:
            continue

        score = cosine_similarity(query_vector, embedding)
        if score > best_score:
            best_score = score
            best_answer = answer

    if best_score >= SIMILARITY_THRESHOLD:
        return best_answer

    return None
