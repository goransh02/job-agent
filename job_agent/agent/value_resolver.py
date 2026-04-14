from __future__ import annotations

from typing import Any

from job_agent.agent.semantic_search import search_similar
from job_agent.ai.llm import ask_llm, ask_llm_json
from job_agent.services.profile_service import get_profile, normalize_profile_id
from job_agent.services.resume_knowledge_service import (
    build_profile_context,
    search_profile_knowledge,
    serialize_knowledge_chunks,
)
from job_agent.services.resume_service import get_resume_upload_path


PROFILE_FIELD_PATHS = {
    "job_source": ("job_source",),
    "summary": ("summary",),
    "first_name": ("first_name",),
    "last_name": ("last_name",),
    "full_name": ("full_name",),
    "email": ("email",),
    "phone": ("phone", "number"),
    "phone_device_type": ("phone", "type"),
    "linkedin": ("linkedin",),
    "github": ("github",),
    "portfolio": ("portfolio",),
    "resume": ("resume_path",),
    "cover_letter": ("cover_letter_path",),
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

RESUME_RAG_FIELD_TYPES = {
    "company_name",
    "job_title",
    "summary",
    "location",
    "start_date_month",
    "start_date_year",
    "end_date_month",
    "end_date_year",
    "current_role",
    "skills",
    "experience_years",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "zip",
    "country",
    "unknown",
}

LEARNED_ANSWER_FIELD_TYPES = {
    "job_source",
    "phone_device_type",
    "notice_period",
    "portfolio",
    "linkedin",
    "github",
}

DEFAULT_FIELD_VALUES = {
    "job_source": "LinkedIn",
    "phone_device_type": "Mobile",
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


def _resolve_from_profile(
    profile: dict[str, Any],
    field_type: str,
    *,
    profile_id: str,
) -> str | None:
    if not profile:
        return None

    if field_type == "resume":
        try:
            return get_resume_upload_path(profile, profile_id=profile_id)
        except Exception:
            return None

    if field_type == "cover_letter":
        cover_letter_path = _format_value(_lookup(profile, ("cover_letter_path",)))
        if cover_letter_path:
            return cover_letter_path
        return None

    if field_type == "country":
        country = _format_value(_lookup(profile, ("address", "country")))
        country_code = _format_value(_lookup(profile, ("phone", "country_code")))

        if country and country_code:
            return f"{country} {country_code}"
        if country_code:
            return country_code
        if country:
            return country

    if field_type == "location":
        parts = [
            _format_value(_lookup(profile, ("address", "city"))),
            _format_value(_lookup(profile, ("address", "state"))),
            _format_value(_lookup(profile, ("address", "country"))),
        ]
        joined = ", ".join(part for part in parts if part)
        return joined or None

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


def _resolve_default_value(profile: dict[str, Any], field_type: str, label: str) -> str | None:
    direct_default = DEFAULT_FIELD_VALUES.get(field_type)
    if direct_default:
        if field_type == "phone_device_type":
            profile_phone_type = _format_value(_lookup(profile, ("phone", "type")))
            return profile_phone_type or direct_default

        profile_value = _format_value(_lookup(profile, (field_type,)))
        return profile_value or direct_default

    normalized_label = " ".join(label.strip().lower().split())

    if "how did you hear" in normalized_label or "where did you hear" in normalized_label:
        profile_value = _format_value(_lookup(profile, ("job_source",)))
        return profile_value or "LinkedIn"

    if "device type" in normalized_label and "phone" in normalized_label:
        profile_value = _format_value(_lookup(profile, ("phone", "type")))
        return profile_value or "Mobile"

    return None


def _build_reasoning_prompt(
    *,
    profile: dict[str, Any],
    label: str,
    field_type: str,
    profile_context: str | None = None,
) -> str:
    prompt = (
        "You are filling a job application form.\n"
        f"Field type: {field_type}\n"
        f"User profile:\n{profile}\n\n"
        f"Form question:\n{label}\n\n"
        "Return JSON with keys `answer` and `confidence`. "
        "If the answer is missing, set `answer` to `UNKNOWN`."
    )
    if profile_context:
        prompt += f"\n\nRelevant profile knowledge:\n{profile_context}"
    return prompt


def _resume_context_as_paragraph(profile_context: str | None) -> str | None:
    if not profile_context:
        return None

    lines = []
    for line in profile_context.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("- "):
            cleaned = cleaned[2:].strip()
        if cleaned.startswith("[") and "]" in cleaned:
            cleaned = cleaned.split("]", 1)[1].strip()
        if cleaned:
            lines.append(cleaned)

    if not lines:
        return None

    paragraph = " ".join(lines)
    return paragraph.strip() or None


def _resolve_from_profile_knowledge(
    *,
    profile_id: str,
    profile: dict[str, Any],
    field_type: str,
    label: str,
) -> dict[str, Any]:
    knowledge_hits = search_profile_knowledge(
        label,
        profile_id=profile_id,
        field_type=field_type,
        top_k=3,
    )
    profile_context = build_profile_context(
        profile_id,
        label,
        field_type=field_type,
        top_k=3,
    )

    if field_type == "summary":
        summary = _resume_context_as_paragraph(profile_context)
        if summary:
            return {
                "value": summary,
                "source": "profile_knowledge",
                "confidence": 0.82,
                "knowledge_hits": serialize_knowledge_chunks(knowledge_hits),
            }

    response = ask_llm_json(
        _build_reasoning_prompt(
            profile=profile,
            label=label,
            field_type=field_type,
            profile_context=profile_context,
        )
    )
    if isinstance(response, dict):
        answer = _format_value(response.get("answer"))
        try:
            confidence = float(response.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if answer and "UNKNOWN" not in answer.upper():
            return {
                "value": answer,
                "source": "groq_reasoning",
                "confidence": max(0.0, min(1.0, confidence or 0.74)),
                "knowledge_hits": serialize_knowledge_chunks(knowledge_hits),
            }

    fallback_response = ask_llm(
        _build_reasoning_prompt(
            profile=profile,
            label=label,
            field_type=field_type,
            profile_context=profile_context,
        )
    )
    if fallback_response and "UNKNOWN" not in fallback_response.upper():
        return {
            "value": fallback_response.strip(),
            "source": "groq_reasoning",
            "confidence": 0.7,
            "knowledge_hits": serialize_knowledge_chunks(knowledge_hits),
        }

    return {
        "value": None,
        "source": "profile_knowledge",
        "confidence": 0.0,
        "knowledge_hits": serialize_knowledge_chunks(knowledge_hits),
    }


def resolve_field(
    field_type: str,
    label: str,
    *,
    profile: dict[str, Any] | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    normalized_profile_id = normalize_profile_id(profile_id or (profile or {}).get("profile_id"))
    current_profile = profile if profile is not None else get_profile(normalized_profile_id)

    direct_value = _resolve_from_profile(
        current_profile,
        field_type,
        profile_id=normalized_profile_id,
    )
    if direct_value:
        return {
            "value": direct_value,
            "source": "profile",
            "confidence": 0.99,
            "knowledge_hits": [],
        }

    default_value = _resolve_default_value(current_profile, field_type, label)
    if default_value:
        return {
            "value": default_value,
            "source": "default",
            "confidence": 0.9,
            "knowledge_hits": [],
        }

    if field_type in LEARNED_ANSWER_FIELD_TYPES:
        learned_value = search_similar(label, profile_id=normalized_profile_id)
        if learned_value:
            return {
                "value": learned_value,
                "source": "learned_answer",
                "confidence": 0.86,
                "knowledge_hits": [],
            }

    if field_type in RESUME_RAG_FIELD_TYPES or field_type not in PROFILE_FIELD_PATHS:
        return _resolve_from_profile_knowledge(
            profile_id=normalized_profile_id,
            profile=current_profile,
            field_type=field_type,
            label=label,
        )

    return {
        "value": None,
        "source": "none",
        "confidence": 0.0,
        "knowledge_hits": [],
    }


def resolve(
    field_type: str,
    label: str,
    profile: dict[str, Any] | None = None,
    *,
    profile_id: str | None = None,
) -> str | None:
    resolution = resolve_field(
        field_type,
        label,
        profile=profile,
        profile_id=profile_id,
    )
    value = resolution.get("value")
    return value if isinstance(value, str) and value.strip() else None
