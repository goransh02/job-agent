from __future__ import annotations

from typing import Any

from job_agent.agent.semantic_search import search_similar
from job_agent.ai.llm import ask_llm
from job_agent.services.profile_service import get_profile


PROFILE_FIELD_PATHS = {
    "first_name": ("first_name",),
    "last_name": ("last_name",),
    "full_name": ("full_name",),
    "email": ("email",),
    "phone": ("phone", "number"),
    "linkedin": ("linkedin",),
    "github": ("github",),
    "portfolio": ("portfolio",),
    "resume": ("resume_path",),
    "address_line1": ("address", "line1"),
    "address_line2": ("address", "line2"),
    "city": ("address", "city"),
    "state": ("address", "state"),
    "zip": ("address", "zip"),
    "country": ("address", "country"),
    "experience_years": ("experience_years",),
    "skills": ("skills",),
    "notice_period": ("notice_period",),
}


def _lookup(profile: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = profile
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _format_value(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(parts) or None

    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None

    return str(value)


def _resolve_from_profile(profile: dict[str, Any], field_type: str) -> str | None:
    if not profile:
        return None

    if field_type == "full_name":
        full_name = _format_value(_lookup(profile, ("full_name",)))
        if full_name:
            return full_name

        parts = [
            _format_value(_lookup(profile, ("first_name",))),
            _format_value(_lookup(profile, ("middle_name",))),
            _format_value(_lookup(profile, ("last_name",))),
        ]
        joined = " ".join(part for part in parts if part)
        return joined or None

    path = PROFILE_FIELD_PATHS.get(field_type)
    if path is None:
        return None

    return _format_value(_lookup(profile, path))


def _build_prompt(profile: dict[str, Any], label: str) -> str:
    return (
        "You are filling a job application form.\n"
        f"User profile:\n{profile}\n\n"
        f"Form question:\n{label}\n\n"
        "Return only the best answer from the profile. "
        "If the profile does not contain the answer, return UNKNOWN."
    )


def resolve(
    field_type: str,
    label: str,
    profile: dict[str, Any] | None = None,
) -> str | None:
    current_profile = profile if profile is not None else get_profile()

    direct_value = _resolve_from_profile(current_profile, field_type)
    if direct_value:
        return direct_value

    learned_value = search_similar(label)
    if learned_value:
        return learned_value

    response = ask_llm(_build_prompt(current_profile, label))
    if response is None or "UNKNOWN" in response.upper():
        return None

    return response.strip()
