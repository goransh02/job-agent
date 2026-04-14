from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

from job_agent.ai.embeddings import generate_embedding
from job_agent.ai.groq import groq_json_completion
from job_agent.agent.semantic_search import cosine_similarity
from job_agent.config import JOB_AGENT_GROQ_CHUNK_MODEL
from job_agent.database.mongo import resume_chunks_collection
from job_agent.models.knowledge_model import KnowledgeChunk, RetrievedKnowledgeChunk
from job_agent.services.profile_service import normalize_profile_id


FIELD_HINTS = {
    "company_name": ("company", "employer", "organization", "worked at"),
    "job_title": ("engineer", "developer", "manager", "analyst", "lead", "intern", "title"),
    "summary": ("summary", "profile", "about", "objective", "built", "designed", "led"),
    "location": ("location", "remote", "hybrid", "onsite", "india", "usa"),
    "skills": ("python", "java", "sql", "skills", "stack", "aws", "react", "docker", "kubernetes"),
    "experience_years": ("years", "experience", "worked for", "career"),
    "start_date_year": ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
    "end_date_year": ("present", "current", "202", "201", "jan", "feb", "mar"),
}


def _clean_text(text: str | None) -> str:
    cleaned = (text or "").replace("\x00", " ")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _strip_rtf(text: str) -> str:
    cleaned = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    cleaned = re.sub(r"\\[a-zA-Z]+\d* ?", " ", cleaned)
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    return _clean_text(cleaned)


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        return ""

    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue

    return _clean_text("\n".join(pages))


def _extract_docx_text(data: bytes) -> str:
    try:
        from docx import Document
    except ImportError:
        return ""

    try:
        document = Document(io.BytesIO(data))
    except Exception:
        return ""

    return _clean_text("\n".join(paragraph.text for paragraph in document.paragraphs))


def extract_resume_text(data: bytes, filename: str | None, content_type: str | None = None) -> str:
    suffix = Path(filename or "").suffix.lower()
    media_type = (content_type or "").lower()

    if suffix in {".txt", ".text"} or media_type.startswith("text/plain"):
        return _clean_text(data.decode("utf-8", errors="ignore"))

    if suffix == ".rtf" or media_type == "application/rtf":
        return _strip_rtf(data.decode("utf-8", errors="ignore"))

    if suffix == ".pdf" or media_type == "application/pdf":
        return _extract_pdf_text(data)

    if suffix == ".docx" or media_type.endswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        return _extract_docx_text(data)

    return ""


def chunk_resume_text(text: str, max_chars: int = 700, overlap: int = 120) -> list[str]:
    normalized = _clean_text(text)
    if not normalized:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n\n+|(?<=\.)\s{2,}", normalized) if part.strip()]
    chunks: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        candidate = f"{buffer} {paragraph}".strip() if buffer else paragraph
        if len(candidate) <= max_chars:
            buffer = candidate
            continue

        if buffer:
            chunks.append(buffer)

        if len(paragraph) <= max_chars:
            buffer = paragraph
            continue

        start = 0
        while start < len(paragraph):
            end = start + max_chars
            chunks.append(paragraph[start:end].strip())
            start = max(end - overlap, 0)
        buffer = ""

    if buffer:
        chunks.append(buffer)

    return [chunk for chunk in chunks if chunk]


def _coarse_sections(text: str, max_chars: int = 2200) -> list[tuple[str | None, str]]:
    normalized = _clean_text(text)
    if not normalized:
        return []

    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    buffer: list[str] = []

    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        is_heading = (
            len(line) <= 80
            and line.upper() == line
            and any(char.isalpha() for char in line)
            and not line.endswith(".")
        )
        if is_heading:
            if buffer:
                sections.append((current_heading, "\n".join(buffer)))
                buffer = []
            current_heading = line.title()
            continue

        if sum(len(item) for item in buffer) + len(line) > max_chars and buffer:
            sections.append((current_heading, "\n".join(buffer)))
            buffer = []
        buffer.append(line)

    if buffer:
        sections.append((current_heading, "\n".join(buffer)))

    if sections:
        return sections

    paragraphs = [part.strip() for part in re.split(r"\n\n+", normalized) if part.strip()]
    return [(None, paragraph) for paragraph in paragraphs]


def _infer_field_types(text: str) -> list[str]:
    lowered = text.lower()
    field_types = [
        field_type
        for field_type, hints in FIELD_HINTS.items()
        if any(hint in lowered for hint in hints)
    ]
    return field_types or ["unknown"]


def _extract_entities(text: str, limit: int = 8) -> list[str]:
    entities: list[str] = []
    for token in re.findall(r"\b[A-Z][a-zA-Z0-9&.+-]{1,}\b", text):
        if token not in entities:
            entities.append(token)
        if len(entities) >= limit:
            break
    return entities


def _extract_date_range(text: str) -> str | None:
    match = re.search(
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{4}\s*[-–]\s*(?:present|current|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{4}|\d{4})|\d{4}\s*[-–]\s*(?:present|current|\d{4}))",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return " ".join(match.group(1).split())
    return None


def _fallback_semantic_chunks(
    *,
    profile_id: str,
    text: str,
    filename: str | None,
    resume_file_id: str | None,
) -> list[KnowledgeChunk]:
    sections = _coarse_sections(text)
    chunks: list[KnowledgeChunk] = []

    for index, (section_title, section_text) in enumerate(sections):
        cleaned_text = _clean_text(section_text)
        if not cleaned_text:
            continue
        field_types = _infer_field_types(cleaned_text)
        summary = cleaned_text[:240]
        metadata = {
            "parser": "fallback",
            "provenance": "heuristic-section-split",
        }
        chunks.append(
            KnowledgeChunk(
                profile_id=profile_id,
                source_type="resume",
                resume_file_id=resume_file_id,
                filename=filename,
                chunk_index=index,
                chunk_text=cleaned_text,
                section_title=section_title,
                field_types=field_types,
                entities=_extract_entities(cleaned_text),
                date_range=_extract_date_range(cleaned_text),
                summary=summary,
                confidence=0.55,
                metadata=metadata,
                embedding=[],
            )
        )

    return chunks


def _semantic_chunk_section(
    *,
    profile_id: str,
    chunk_offset: int,
    section_title: str | None,
    section_text: str,
    filename: str | None,
    resume_file_id: str | None,
) -> list[KnowledgeChunk]:
    system_prompt = (
        "You convert resume sections into concise, field-relevant semantic chunks for job-form autofill. "
        "Return valid JSON with a top-level `chunks` array only."
    )
    user_prompt = (
        "Split the following resume section into small, self-contained chunks that help answer job application "
        "fields. Each chunk must include `chunk_text`, `section_title`, `field_types`, `entities`, `date_range`, "
        "`summary`, and `confidence`.\n\n"
        "Rules:\n"
        "- `field_types` should be a short list using labels like company_name, job_title, summary, location, "
        "skills, experience_years, start_date_year, end_date_year, current_role, unknown.\n"
        "- `confidence` must be between 0 and 1.\n"
        "- Keep chunk_text focused and avoid merging unrelated jobs.\n\n"
        f"Section title: {section_title or 'Unknown'}\n"
        f"Section text:\n{section_text}"
    )
    response = groq_json_completion(
        model=JOB_AGENT_GROQ_CHUNK_MODEL,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
    )
    if not isinstance(response, dict):
        return []

    raw_chunks = response.get("chunks")
    if not isinstance(raw_chunks, list):
        return []

    chunks: list[KnowledgeChunk] = []
    for index, raw_chunk in enumerate(raw_chunks, start=chunk_offset):
        if not isinstance(raw_chunk, dict):
            continue
        chunk_text = _clean_text(raw_chunk.get("chunk_text"))
        if not chunk_text:
            continue

        field_types = raw_chunk.get("field_types")
        if not isinstance(field_types, list):
            field_types = _infer_field_types(chunk_text)

        entities = raw_chunk.get("entities")
        if not isinstance(entities, list):
            entities = _extract_entities(chunk_text)

        confidence = raw_chunk.get("confidence", 0.0)
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.0

        metadata = {
            "parser": "groq",
            "provenance": "semantic-section-split",
        }
        chunks.append(
            KnowledgeChunk(
                profile_id=profile_id,
                source_type="resume",
                resume_file_id=resume_file_id,
                filename=filename,
                chunk_index=index,
                chunk_text=chunk_text,
                section_title=_clean_text(raw_chunk.get("section_title")) or section_title,
                field_types=[str(item).strip() for item in field_types if str(item).strip()],
                entities=[str(item).strip() for item in entities if str(item).strip()],
                date_range=_clean_text(raw_chunk.get("date_range")) or _extract_date_range(chunk_text),
                summary=_clean_text(raw_chunk.get("summary")) or chunk_text[:240],
                confidence=max(0.0, min(1.0, confidence_value)),
                metadata=metadata,
                embedding=[],
            )
        )

    return chunks


def semantic_chunk_resume(
    text: str,
    *,
    profile_id: str | None = None,
    filename: str | None = None,
    resume_file_id: str | None = None,
) -> list[KnowledgeChunk]:
    normalized_profile_id = normalize_profile_id(profile_id)
    sections = _coarse_sections(text)
    if not sections:
        return []

    all_chunks: list[KnowledgeChunk] = []
    for section_title, section_text in sections:
        chunk_offset = len(all_chunks)
        semantic_chunks = _semantic_chunk_section(
            profile_id=normalized_profile_id,
            chunk_offset=chunk_offset,
            section_title=section_title,
            section_text=section_text,
            filename=filename,
            resume_file_id=resume_file_id,
        )
        if semantic_chunks:
            all_chunks.extend(semantic_chunks)
            continue

        fallback_chunks = _fallback_semantic_chunks(
            profile_id=normalized_profile_id,
            text=section_text,
            filename=filename,
            resume_file_id=resume_file_id,
        )
        for fallback_chunk in fallback_chunks:
            fallback_chunk.chunk_index = len(all_chunks)
            fallback_chunk.section_title = fallback_chunk.section_title or section_title
            all_chunks.append(fallback_chunk)

    return all_chunks


def clear_resume_knowledge(profile_id: str | None = None) -> None:
    resume_chunks_collection.delete_many(
        {
            "profile_id": normalize_profile_id(profile_id),
            "source_type": "resume",
        }
    )


def index_resume_content(
    data: bytes,
    filename: str | None,
    content_type: str | None = None,
    *,
    profile_id: str | None = None,
    resume_file_id: str | None = None,
) -> int:
    normalized_profile_id = normalize_profile_id(profile_id)
    text = extract_resume_text(data, filename, content_type)
    if not text:
        clear_resume_knowledge(normalized_profile_id)
        return 0

    chunks = semantic_chunk_resume(
        text,
        profile_id=normalized_profile_id,
        filename=filename,
        resume_file_id=resume_file_id,
    )
    clear_resume_knowledge(normalized_profile_id)

    for chunk in chunks:
        chunk.embedding = generate_embedding(
            "\n".join(
                part
                for part in [
                    chunk.section_title or "",
                    chunk.summary or "",
                    chunk.chunk_text,
                    " ".join(chunk.field_types),
                    " ".join(chunk.entities),
                ]
                if part
            )
        )
        resume_chunks_collection.insert_one(chunk.model_dump())

    return len(chunks)


def ensure_resume_knowledge_index(
    profile: dict | None = None,
    *,
    profile_id: str | None = None,
) -> int:
    normalized_profile_id = normalize_profile_id(profile_id or (profile or {}).get("profile_id"))
    existing = resume_chunks_collection.count_documents(
        {
            "profile_id": normalized_profile_id,
            "source_type": "resume",
        }
    )
    if existing:
        return existing

    from job_agent.services.resume_service import get_resume_upload_path

    upload_path = get_resume_upload_path(profile, profile_id=normalized_profile_id)
    if not upload_path:
        return 0

    path = Path(upload_path)
    if not path.exists():
        return 0

    return index_resume_content(
        path.read_bytes(),
        path.name,
        profile_id=normalized_profile_id,
        resume_file_id=(profile or {}).get("resume_file_id"),
    )


def search_profile_knowledge(
    query: str | None,
    *,
    profile_id: str | None = None,
    field_type: str | None = None,
    top_k: int = 3,
) -> list[RetrievedKnowledgeChunk]:
    if not query:
        return []

    normalized_profile_id = normalize_profile_id(profile_id)
    ensure_resume_knowledge_index(profile_id=normalized_profile_id)
    query_embedding = generate_embedding(query)
    query_tokens = set(re.findall(r"[a-z0-9]{3,}", query.lower()))
    ranked: list[RetrievedKnowledgeChunk] = []

    try:
        documents = resume_chunks_collection.find(
            {
                "profile_id": normalized_profile_id,
                "source_type": "resume",
            }
        )
    except Exception:
        return []

    for document in documents:
        # Remove MongoDB's _id field if present
        document.pop("_id", None)
        
        embedding = document.get("embedding")
        chunk_text = document.get("chunk_text") or document.get("content")
        if not embedding or not chunk_text:
            continue

        score = cosine_similarity(query_embedding, embedding)
        field_types = [
            str(item).strip()
            for item in (document.get("field_types") or [])
            if str(item).strip()
        ]
        lexical_blob = " ".join(
            part
            for part in [
                str(chunk_text),
                str(document.get("summary") or ""),
                " ".join(str(item) for item in document.get("entities") or []),
            ]
            if part
        ).lower()
        chunk_tokens = set(re.findall(r"[a-z0-9]{3,}", lexical_blob))
        lexical_overlap = (
            len(query_tokens & chunk_tokens) / len(query_tokens)
            if query_tokens
            else 0.0
        )

        if field_type and field_type in field_types:
            score += 0.15
        if field_type and field_type == "summary" and document.get("summary"):
            score += 0.05
        if lexical_overlap:
            score += lexical_overlap * 0.25
        elif query_tokens and (not field_type or field_type not in field_types):
            score *= 0.05

        chunk_document = dict(document)
        chunk_document.setdefault("chunk_text", chunk_text)
        chunk_document.setdefault("profile_id", normalized_profile_id)
        chunk_document.setdefault("field_types", field_types)
        chunk_document.setdefault("source_type", "resume")
        ranked.append(
            RetrievedKnowledgeChunk(
                score=score,
                chunk=KnowledgeChunk(**chunk_document),
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return [item for item in ranked[:top_k] if item.score > 0.1]


def build_profile_context(
    profile_id: str | None,
    query: str | None,
    *,
    field_type: str | None = None,
    top_k: int = 3,
) -> str | None:
    matches = search_profile_knowledge(
        query,
        profile_id=profile_id,
        field_type=field_type,
        top_k=top_k,
    )
    if not matches:
        return None

    snippets = []
    for match in matches:
        chunk = match.chunk
        label = chunk.section_title or "Resume"
        summary = chunk.summary or chunk.chunk_text
        snippets.append(f"- [{label}] {summary}")

    return "\n".join(snippets) or None


def search_resume_context(
    query: str | None,
    top_k: int = 3,
    *,
    profile_id: str | None = None,
    field_type: str | None = None,
) -> list[dict[str, object]]:
    matches = search_profile_knowledge(
        query,
        profile_id=profile_id,
        field_type=field_type,
        top_k=top_k,
    )
    return [
        {
            "score": match.score,
            "content": match.chunk.chunk_text,
            "summary": match.chunk.summary,
            "field_types": match.chunk.field_types,
            "chunk_index": match.chunk.chunk_index,
        }
        for match in matches
    ]


def build_resume_context(
    query: str | None,
    top_k: int = 3,
    *,
    profile_id: str | None = None,
    field_type: str | None = None,
) -> str | None:
    return build_profile_context(
        profile_id,
        query,
        field_type=field_type,
        top_k=top_k,
    )


def serialize_knowledge_chunks(chunks: list[RetrievedKnowledgeChunk]) -> list[dict[str, Any]]:
    return [
        {
            "score": chunk.score,
            "chunk": json.loads(chunk.chunk.model_dump_json()),
        }
        for chunk in chunks
    ]
