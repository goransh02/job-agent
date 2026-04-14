from __future__ import annotations

from job_agent.ai.embeddings import generate_embedding
from job_agent.services.profile_service import normalize_profile_id
from job_agent.database.mongo import answers_collection


def store_answer(question: str, answer: str, profile_id: str | None = None) -> None:
    vector = generate_embedding(question)

    answers_collection.insert_one(
        {
            "profile_id": normalize_profile_id(profile_id),
            "question": question,
            "embedding": vector,
            "answer": answer,
        }
    )
