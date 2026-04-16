from __future__ import annotations

from typing import Any

from job_agent.config import DEFAULT_PROFILE_ID
from job_agent.database.mongo import profile_collection


def normalize_profile_id(profile_id: str | None = None) -> str:
    cleaned = str(profile_id or DEFAULT_PROFILE_ID).strip()
    return cleaned or DEFAULT_PROFILE_ID


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Deep merge source dict into target dict."""
    result = dict(target)
    for key, value in source.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _legacy_default_profile() -> dict[str, Any]:
    profile = profile_collection.find_one() or {}
    if not isinstance(profile, dict):
        return {}
    if profile.get("profile_id"):
        return {}
    return profile


def get_profile(profile_id: str | None = None) -> dict[str, Any]:
    normalized_profile_id = normalize_profile_id(profile_id)
    try:
        profile = profile_collection.find_one({"profile_id": normalized_profile_id}) or {}
        if not profile and normalized_profile_id == DEFAULT_PROFILE_ID:
            profile = _legacy_default_profile()
    except Exception:
        return {}

    if not isinstance(profile, dict):
        return {}

    profile.pop("_id", None)
    profile["profile_id"] = normalized_profile_id
    return profile


def save_profile(profile: dict[str, Any], profile_id: str | None = None) -> None:
    normalized_profile_id = normalize_profile_id(profile_id or profile.get("profile_id"))
    existing = get_profile(normalized_profile_id)
    clean_profile = dict(profile)
    clean_profile["profile_id"] = normalized_profile_id

    existing_document = profile_collection.find_one({"profile_id": normalized_profile_id})
    if not existing_document and normalized_profile_id == DEFAULT_PROFILE_ID:
        existing_document = _legacy_default_profile()

    if existing_document and isinstance(existing_document, dict) and "_id" in existing_document:
        clean_profile["_id"] = existing_document["_id"]
        profile_collection.replace_one(
            {"_id": existing_document["_id"]},
            clean_profile,
            upsert=True,
        )
        return

    if existing and isinstance(existing, dict) and existing.get("profile_id") == normalized_profile_id:
        profile_collection.replace_one({"profile_id": normalized_profile_id}, clean_profile, upsert=True)
        return

    profile_collection.replace_one({"profile_id": normalized_profile_id}, clean_profile, upsert=True)


def update_profile_fields(
    fields: dict[str, Any],
    profile_id: str | None = None,
) -> dict[str, Any]:
    normalized_profile_id = normalize_profile_id(profile_id or fields.get("profile_id"))
    profile = get_profile(normalized_profile_id)
    profile = _deep_merge(profile, fields)
    save_profile(profile, profile_id=normalized_profile_id)
    return profile
