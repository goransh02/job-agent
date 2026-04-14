from __future__ import annotations

from typing import Any

from job_agent.agent.field_classifier import classify
from job_agent.agent.value_resolver import resolve
from job_agent.services.profile_service import get_profile, normalize_profile_id


MANUAL_FIELD_TYPES = {"resume", "cover_letter"}


def _normalize_options(field: dict[str, Any]) -> list[str]:
    options = field.get("options") or []
    if not isinstance(options, list):
        return []
    return [str(option).strip() for option in options if str(option).strip()]


def build_extension_fill_plan(
    url: str,
    fields: list[dict[str, Any]],
    *,
    profile: dict[str, Any] | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    normalized_profile_id = normalize_profile_id(profile_id or (profile or {}).get("profile_id"))
    current_profile = profile if profile is not None else get_profile(normalized_profile_id)
    fills: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for field in fields:
        field_id = str(field.get("field_id") or "").strip()
        label = str(field.get("label") or "").strip()
        tag_name = str(field.get("tag_name") or "").strip().lower()
        input_type = str(field.get("input_type") or "").strip().lower()
        role = str(field.get("role") or "").strip().lower()
        required = bool(field.get("required"))
        options = _normalize_options(field)
        field_type = classify(label)

        base_payload = {
            "field_id": field_id,
            "label": label,
            "field_type": field_type,
            "tag_name": tag_name,
            "input_type": input_type,
            "role": role,
            "required": required,
            "options": options,
        }

        if field_type in MANUAL_FIELD_TYPES:
            target_list = blocked if required else skipped
            target_list.append(
                {
                    **base_payload,
                    "reason": "manual_upload_required",
                    "message": "Document upload is still handled manually in the extension flow.",
                }
            )
            continue

        value = resolve(
            field_type,
            label,
            profile=current_profile,
            profile_id=normalized_profile_id,
        )
        if value in (None, ""):
            target_list = blocked if required else skipped
            target_list.append(
                {
                    **base_payload,
                    "reason": "missing_value",
                    "message": "No reliable answer was found for this field.",
                }
            )
            continue

        fills.append(
            {
                **base_payload,
                "value": value,
            }
        )

    return {
        "url": url,
        "profile_id": normalized_profile_id,
        "fills": fills,
        "blocked": blocked,
        "skipped": skipped,
        "stats": {
            "fields_seen": len(fields),
            "fills": len(fills),
            "blocked": len(blocked),
            "skipped": len(skipped),
        },
    }
