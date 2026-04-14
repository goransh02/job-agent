from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from job_agent.database.mongo import applications_collection
from job_agent.services.profile_service import normalize_profile_id


def create_application_id() -> str:
    return uuid4().hex


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_state_for_storage(state: dict[str, Any]) -> dict[str, Any]:
    document = dict(state)
    fields = []
    for field in document.get("fields") or []:
        serialized = {
            key: value
            for key, value in dict(field).items()
            if key != "element"
        }
        fields.append(serialized)
    document["fields"] = fields
    document["resolved_values"] = [
        {
            key: (
                value.model_dump()
                if hasattr(value, "model_dump")
                else value
            )
            for key, value in dict(resolved).items()
            if key != "element"
        }
        for resolved in document.get("resolved_values") or []
    ]

    document.pop("browser", None)
    document.pop("websocket", None)
    document["pending_questions"] = [
        question.model_dump() if hasattr(question, "model_dump") else dict(question)
        for question in document.get("pending_questions") or []
    ]
    document["knowledge_hits"] = [
        hit.model_dump() if hasattr(hit, "model_dump") else hit
        for hit in document.get("knowledge_hits") or []
    ]
    document["profile_id"] = normalize_profile_id(document.get("profile_id"))
    document["updated_at"] = _timestamp()
    document.setdefault("created_at", document["updated_at"])
    return document


def save_application_state(state: dict[str, Any]) -> dict[str, Any]:
    document = _sanitize_state_for_storage(state)
    applications_collection.replace_one(
        {"application_id": document["application_id"]},
        document,
        upsert=True,
    )
    return document


def load_application_state(application_id: str) -> dict[str, Any] | None:
    document = applications_collection.find_one({"application_id": application_id})
    if not isinstance(document, dict):
        return None
    document.pop("_id", None)
    return document
