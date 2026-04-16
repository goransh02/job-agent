from __future__ import annotations

from typing import Any

from job_agent.agent.field_classifier import classify
from job_agent.agent.value_resolver import PROFILE_FIELD_PATHS, resolve
from job_agent.services.profile_service import get_profile, normalize_profile_id


MANUAL_FIELD_TYPES = {"resume", "cover_letter"}


def _normalize_options(field: dict[str, Any]) -> list[str]:
    options = field.get("options") or []
    if not isinstance(options, list):
        return []
    return [str(option).strip() for option in options if str(option).strip()]


def normalize_user_values(user_values: dict[str, str]) -> dict[str, Any]:
    """
    Convert user-provided field label -> value mapping into profile structure.
    
    Example:
        {"First Name": "John", "Email": "john@example.com"} 
        -> {"first_name": "John", "email": "john@example.com"}
    """
    if not user_values:
        return {}
    
    profile_updates = {}
    
    for label, value in user_values.items():
        if not label or not str(value).strip():
            continue
        
        # Classify the field to determine field type
        field_type = classify(label)
        
        # Look up the profile path for this field type
        if field_type not in PROFILE_FIELD_PATHS:
            # For unknown field types, use the field type as a simple key
            profile_updates[field_type] = str(value).strip()
            continue
        
        # Get the nested path for this field type
        path = PROFILE_FIELD_PATHS[field_type]
        
        if len(path) == 1:
            # Simple top-level field
            profile_updates[path[0]] = str(value).strip()
        else:
            # Nested field (e.g., address.city)
            # Create nested structure
            if path[0] not in profile_updates:
                profile_updates[path[0]] = {}
            
            # Navigate to the parent level
            current = profile_updates[path[0]]
            for key in path[1:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            
            # Set the final value
            current[path[-1]] = str(value).strip()
    
    return profile_updates


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
