from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class KnowledgeChunk:
    profile_id: str
    source_type: str = "resume"
    resume_file_id: str | None = None
    filename: str | None = None
    chunk_index: int = 0
    chunk_text: str = ""
    section_title: str | None = None
    field_types: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    date_range: str | None = None
    summary: str | None = None
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump())


@dataclass
class RetrievedKnowledgeChunk:
    score: float
    chunk: KnowledgeChunk

    def model_dump(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "chunk": self.chunk.model_dump(),
        }
