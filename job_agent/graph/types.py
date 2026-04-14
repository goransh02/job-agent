from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolCallResult:
    tool_name: str
    success: bool
    data: Any = None
    error: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HumanEscalation:
    field_id: str
    label: str
    field_type: str
    reason: str
    confidence: float = 0.0
    retry_count: int = 0

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ApplicationGraphState:
    application_id: str
    profile_id: str
    platform: str
    job_url: str
    fields: list[dict[str, Any]] = field(default_factory=list)
    field_plan: list[dict[str, Any]] = field(default_factory=list)
    resolved_values: list[dict[str, Any]] = field(default_factory=list)
    knowledge_hits: list[dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0
    pending_questions: list[HumanEscalation] = field(default_factory=list)
    browser_snapshot: dict[str, Any] = field(default_factory=dict)
    submitted: bool = False
    stop_reason: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)
