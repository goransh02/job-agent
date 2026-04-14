from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Any

from job_agent.database.mongo import has_mongo_storage, has_resume_bucket, resume_bucket
from job_agent.services.profile_service import get_profile, normalize_profile_id, update_profile_fields
from job_agent.services.resume_knowledge_service import index_resume_content


class ResumeStorageError(RuntimeError):
    pass


def _to_object_id(value: str):
    try:
        from bson import ObjectId
    except ImportError:
        return value

    try:
        return ObjectId(value)
    except Exception as exc:
        raise ResumeStorageError(f"Invalid resume file id: {value}") from exc


def _safe_filename(filename: str | None) -> str:
    cleaned = Path(filename or "resume.pdf").name.strip()
    return cleaned or "resume.pdf"


def _resume_temp_path(profile_id: str, file_id: str, filename: str) -> Path:
    suffix = Path(filename).suffix or ".pdf"
    temp_dir = Path(tempfile.gettempdir()) / "job_agent_resumes"
    temp_dir.mkdir(parents=True, exist_ok=True)
    safe_profile_id = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in profile_id)
    return temp_dir / f"{safe_profile_id}-{file_id}{suffix}"


def store_resume(
    data: bytes,
    filename: str | None,
    content_type: str | None = None,
    attach_to_profile: bool = True,
    profile_id: str | None = None,
) -> dict[str, Any]:
    if not data:
        raise ResumeStorageError("Resume file is empty")

    if not has_mongo_storage() or not has_resume_bucket():
        raise ResumeStorageError("MongoDB resume storage is unavailable")

    normalized_profile_id = normalize_profile_id(profile_id)
    stored_filename = _safe_filename(filename)
    metadata = {
        "content_type": content_type or "application/octet-stream",
        "profile_id": normalized_profile_id,
    }

    upload_id = resume_bucket.upload_from_stream(
        stored_filename,
        io.BytesIO(data),
        metadata=metadata,
    )

    payload = {
        "profile_id": normalized_profile_id,
        "resume_file_id": str(upload_id),
        "resume_filename": stored_filename,
        "resume_content_type": metadata["content_type"],
        "resume_size_bytes": len(data),
    }

    if attach_to_profile:
        profile = get_profile(normalized_profile_id)
        previous_file_id = profile.get("resume_file_id")
        update_profile_fields(
            {
                **payload,
                "resume_path": None,
            },
            profile_id=normalized_profile_id,
        )

        if previous_file_id and previous_file_id != payload["resume_file_id"]:
            try:
                resume_bucket.delete(_to_object_id(previous_file_id))
            except Exception:
                pass

    try:
        index_resume_content(
            data,
            stored_filename,
            content_type,
            profile_id=normalized_profile_id,
            resume_file_id=payload["resume_file_id"],
        )
    except Exception:
        pass

    return payload


def get_resume_metadata(
    profile: dict[str, Any] | None = None,
    *,
    profile_id: str | None = None,
) -> dict[str, Any] | None:
    normalized_profile_id = normalize_profile_id(profile_id or (profile or {}).get("profile_id"))
    current_profile = profile if profile is not None else get_profile(normalized_profile_id)
    file_id = current_profile.get("resume_file_id")
    if not file_id:
        return None

    return {
        "profile_id": normalized_profile_id,
        "resume_file_id": file_id,
        "resume_filename": current_profile.get("resume_filename"),
        "resume_content_type": current_profile.get("resume_content_type"),
        "resume_size_bytes": current_profile.get("resume_size_bytes"),
    }


def get_resume_upload_path(
    profile: dict[str, Any] | None = None,
    *,
    profile_id: str | None = None,
) -> str | None:
    normalized_profile_id = normalize_profile_id(profile_id or (profile or {}).get("profile_id"))
    current_profile = profile if profile is not None else get_profile(normalized_profile_id)

    resume_path = current_profile.get("resume_path")
    if resume_path:
        path = Path(str(resume_path))
        if path.exists():
            return str(path)

    file_id = current_profile.get("resume_file_id")
    if not file_id:
        return None

    if not has_mongo_storage() or not has_resume_bucket():
        raise ResumeStorageError("Stored resume exists but MongoDB resume storage is unavailable")

    filename = current_profile.get("resume_filename") or "resume.pdf"
    target_path = _resume_temp_path(normalized_profile_id, file_id, filename)

    if target_path.exists():
        return str(target_path)

    object_id = _to_object_id(file_id)
    buffer = io.BytesIO()
    try:
        resume_bucket.download_to_stream(object_id, buffer)
    except Exception as exc:
        raise ResumeStorageError(f"Unable to download resume {file_id}") from exc

    target_path.write_bytes(buffer.getvalue())
    return str(target_path)
