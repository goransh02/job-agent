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


def _is_serializable(obj: Any) -> bool:
    """Check if an object is BSON/JSON serializable."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return True
    if isinstance(obj, dict):
        return all(_is_serializable(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return all(_is_serializable(v) for v in obj)
    return False


def _make_serializable(obj: Any) -> Any:
    """Convert non-serializable objects to serializable equivalents."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items() if _is_serializable(v) or isinstance(v, dict) or isinstance(v, (list, tuple))}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj if _is_serializable(v) or isinstance(v, (dict, list, tuple))]
    # For non-serializable objects, try to get their representation
    return None


def _sanitize_state_for_storage(state: dict[str, Any]) -> dict[str, Any]:
    document = dict(state)
    
    # Remove non-serializable objects first
    document.pop("browser", None)
    document.pop("websocket", None)
    document.pop("tools", None)
    document.pop("graph", None)
    document.pop("runner", None)
    
    # Remove any private/internal fields
    for key in list(document.keys()):
        if key.startswith("_") and not key.startswith("__"):
            document.pop(key, None)
    
    # Sanitize fields - remove element references and non-serializable objects
    fields = []
    for field in document.get("fields") or []:
        if isinstance(field, dict):
            serialized = {
                key: value
                for key, value in field.items()
                if key != "element" and not key.startswith("_") and _is_serializable(value)
            }
            fields.append(serialized)
    document["fields"] = fields
    
    # Sanitize resolved values
    document["resolved_values"] = [
        {
            key: (
                value.model_dump()
                if hasattr(value, "model_dump")
                else value
            )
            for key, value in dict(resolved).items()
            if key != "element" and _is_serializable(value) if not hasattr(value, "model_dump")
        }
        for resolved in document.get("resolved_values") or []
    ]
    
    # Make all remaining values serializable
    for key in list(document.keys()):
        value = document[key]
        if not _is_serializable(value) and not isinstance(value, (list, dict)):
            document.pop(key, None)
        elif isinstance(value, dict):
            document[key] = _make_serializable(value)
        elif isinstance(value, list):
            document[key] = _make_serializable(value)
    
    # Handle pending questions and knowledge hits
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
