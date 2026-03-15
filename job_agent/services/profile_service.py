from __future__ import annotations

from typing import Any

from job_agent.database.mongo import profile_collection


def get_profile() -> dict[str, Any]:
    try:
        profile = profile_collection.find_one() or {}
    except Exception:
        return {}

    if not isinstance(profile, dict):
        return {}

    profile.pop("_id", None)
    return profile


def save_profile(profile: dict[str, Any]) -> None:
    existing = profile_collection.find_one()
    clean_profile = dict(profile)

    if existing and isinstance(existing, dict) and "_id" in existing:
        profile_collection.replace_one(
            {"_id": existing["_id"]},
            clean_profile,
            upsert=True,
        )
        return

    profile_collection.replace_one({}, clean_profile, upsert=True)
