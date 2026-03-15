from __future__ import annotations

from job_agent.ai.embeddings import generate_embedding
from job_agent.database.mongo import answers_collection


def store_answer(question: str, answer: str) -> None:
    vector = generate_embedding(question)

    answers_collection.insert_one(
        {
            "question": question,
            "embedding": vector,
            "answer": answer,
        }
    )
