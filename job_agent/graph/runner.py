from __future__ import annotations

from typing import Any

from job_agent.agent.cookie_handler import accept_cookies
from job_agent.agent.field_classifier import classify
from job_agent.agent.login_handler import attempt_login
from job_agent.agent.learning_engine import store_answer
from job_agent.agent.register_handler import attempt_register
from job_agent.agent.value_resolver import resolve_field
from job_agent.browser.playwright_browser import Browser
from job_agent.config import AUTO_SUBMIT, BROWSER_STEP_WAIT_TIMEOUT_MS
from job_agent.graph.playwright_tools import PlaywrightToolRegistry
from job_agent.graph.types import HumanEscalation
from job_agent.services.application_service import create_application_id, save_application_state
from job_agent.services.profile_service import normalize_profile_id

try:
    from langgraph.graph import END, START, StateGraph

    HAS_LANGGRAPH = True
except ImportError:  # pragma: no cover - exercised indirectly via fallback
    END = "__end__"
    START = "__start__"
    StateGraph = None
    HAS_LANGGRAPH = False


class _FallbackCompiledGraph:
    def __init__(self, runner: "ApplicationGraphRunner") -> None:
        self.runner = runner

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        current = "bootstrap"
        while current != END:
            node = getattr(self.runner, current)
            state = await node(state)
            current = self.runner.next_node(current, state)
        return state


class ApplicationGraphRunner:
    def __init__(
        self,
        *,
        platform: str,
        websocket=None,
        browser: Browser | None = None,
        auto_submit: bool | None = None,
    ) -> None:
        self.platform = platform
        self.websocket = websocket
        self.browser = browser or Browser()
        self.auto_submit = AUTO_SUBMIT if auto_submit is None else auto_submit
        self.tools = PlaywrightToolRegistry(self.browser)
        self.graph = self._compile_graph()

    def build_initial_state(
        self,
        *,
        job_url: str,
        profile_id: str | None,
        application_id: str | None = None,
        continued: bool = False,
    ) -> dict[str, Any]:
        resolved_profile_id = normalize_profile_id(profile_id)
        app_id = application_id or create_application_id()
        return {
            "application_id": app_id,
            "profile_id": resolved_profile_id,
            "platform": self.platform,
            "job_url": job_url,
            "fields": [],
            "field_plan": [],
            "resolved_values": [],
            "knowledge_hits": [],
            "retry_count": 0,
            "pending_questions": [],
            "browser_snapshot": {},
            "submitted": False,
            "stop_reason": None,
            "allow_apply_click": not continued,
            "auth_gate_handled": False,
            "continue_loop": True,
            "count_step": True,
            "current_step": 0,
            "continued": continued,
            "result": {
                "application_id": app_id,
                "profile_id": resolved_profile_id,
                "platform": self.platform,
                "url": job_url,
                "apply_clicked": False,
                "auth_gate_handled": False,
                "resume_uploaded": False,
                "cover_letter_uploaded": False,
                "can_continue": True,
                "browser_headless": self.browser.headless,
                "browser_mode": getattr(self.browser, "mode", "unknown"),
                "fields_detected": 0,
                "fields_filled": 0,
                "questions_asked": 0,
                "steps_processed": 0,
                "steps_advanced": 0,
                "submitted": False,
                "stopped_reason": None,
                "continued": continued,
            },
        }

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        final_state = await self.graph.ainvoke(state)
        result = dict(final_state["result"])
        result["submitted"] = final_state.get("submitted", result.get("submitted", False))
        result["stopped_reason"] = final_state.get("stop_reason")
        result["pending_questions"] = [
            question.model_dump() if hasattr(question, "model_dump") else dict(question)
            for question in final_state.get("pending_questions") or []
        ]
        return result

    def _compile_graph(self):
        if not HAS_LANGGRAPH:
            return _FallbackCompiledGraph(self)

        workflow = StateGraph(dict)
        workflow.add_node("bootstrap", self.bootstrap)
        workflow.add_node("read_page", self.read_page)
        workflow.add_node("plan_fields", self.plan_fields)
        workflow.add_node("retrieve_profile_context", self.retrieve_profile_context)
        workflow.add_node("fill_fields", self.fill_fields)
        workflow.add_node("evaluate_page", self.evaluate_page)
        workflow.add_node("assess_gaps", self.assess_gaps)
        workflow.add_node("human_pause", self.human_pause)
        workflow.add_node("advance_or_submit", self.advance_or_submit)

        workflow.add_edge(START, "bootstrap")
        workflow.add_edge("bootstrap", "read_page")
        workflow.add_edge("read_page", "plan_fields")
        workflow.add_edge("plan_fields", "retrieve_profile_context")
        workflow.add_edge("retrieve_profile_context", "fill_fields")
        workflow.add_edge("fill_fields", "evaluate_page")
        workflow.add_edge("evaluate_page", "assess_gaps")
        workflow.add_conditional_edges(
            "assess_gaps",
            lambda state: self.next_node("assess_gaps", state),
            {
                "human_pause": "human_pause",
                "advance_or_submit": "advance_or_submit",
                END: END,
            },
        )
        workflow.add_conditional_edges(
            "human_pause",
            lambda state: self.next_node("human_pause", state),
            {
                "fill_fields": "fill_fields",
                END: END,
            },
        )
        workflow.add_conditional_edges(
            "advance_or_submit",
            lambda state: self.next_node("advance_or_submit", state),
            {
                "read_page": "read_page",
                END: END,
            },
        )
        return workflow.compile()

    def next_node(self, current: str, state: dict[str, Any]) -> str:
        if current == "bootstrap":
            if state.get("stop_reason"):
                return END
            return "read_page"
        if current == "read_page":
            return "plan_fields"
        if current == "plan_fields":
            return "retrieve_profile_context"
        if current == "retrieve_profile_context":
            return "fill_fields"
        if current == "fill_fields":
            return "evaluate_page"
        if current == "evaluate_page":
            return "assess_gaps"
        if current == "assess_gaps":
            if state.get("stop_reason") == "no_fields_detected":
                return END
            if state.get("pending_questions"):
                return "human_pause"
            return "advance_or_submit"
        if current == "human_pause":
            return END if state.get("stop_reason") else "fill_fields"
        if current == "advance_or_submit":
            return "read_page" if state.get("continue_loop") else END
        return END

    async def send(self, message: str, event_type: str = "status", **payload) -> None:
        if self.websocket is None:
            return
        body = {"type": event_type, "message": message}
        body.update(payload)
        await self.websocket.send_json(body)

    async def _persist(self, state: dict[str, Any]) -> dict[str, Any]:
        save_application_state(state)
        return state

    async def bootstrap(self, state: dict[str, Any]) -> dict[str, Any]:
        await self.send(f"Browser mode: {getattr(self.browser, 'mode', 'unknown')}")
        if state.get("continued"):
            await self.send("Resuming LangGraph application run")
        else:
            await self.send(f"Opening {self.platform} job page")
            result = await self.tools.call("open_job", url=state["job_url"])
            if not result.success:
                state["stop_reason"] = "open_failed"
                state["result"]["stopped_reason"] = "open_failed"
        return await self._persist(state)

    async def _preprocess_page(self) -> None:
        try:
            await accept_cookies(self.browser.page)
        except Exception:
            pass

    async def _handle_auth_gate(self, state: dict[str, Any]) -> None:
        if state.get("auth_gate_handled"):
            return
        try:
            has_auth_gate = await self.browser.has_auth_gate()
        except Exception:
            return

        if not has_auth_gate:
            return

        state["auth_gate_handled"] = True
        state["result"]["auth_gate_handled"] = True
        await self.send("Account gate detected; attempting auto-continue")

        try:
            if await self.browser.click_create_account():
                await self.tools.call("wait_for_form", timeout_ms=BROWSER_STEP_WAIT_TIMEOUT_MS)
        except Exception:
            pass

        if await attempt_register(self.browser.page) or await attempt_login(self.browser.page):
            await self.tools.call("wait_for_form", timeout_ms=BROWSER_STEP_WAIT_TIMEOUT_MS)

    def _document_fields(self) -> list[dict[str, Any]]:
        return [
            {
                "field_id": "resume-upload",
                "label": "Resume/CV",
                "tag_name": "input",
                "input_type": "file",
                "role": "",
                "required": True,
                "options": [],
                "element": None,
            },
            {
                "field_id": "cover-letter-upload",
                "label": "Cover Letter",
                "tag_name": "input",
                "input_type": "file",
                "role": "",
                "required": False,
                "options": [],
                "element": None,
            },
        ]

    async def _read_fields(self, state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        snapshot_result = await self.tools.call("snapshot_form")
        page_result = await self.tools.call("read_page")
        fields = list(snapshot_result.data or []) if snapshot_result.success else []
        browser_snapshot = page_result.data or {}

        if not fields:
            document_fields = []
            if await self.browser.has_document_upload_controls("resume"):
                document_fields.append(self._document_fields()[0])
            if await self.browser.has_document_upload_controls("cover_letter"):
                document_fields.append(self._document_fields()[1])
            if document_fields:
                fields = document_fields
                browser_snapshot = dict(browser_snapshot)
                browser_snapshot["field_count"] = len(fields)
                browser_snapshot["fields"] = [
                    {
                        "field_id": field["field_id"],
                        "label": field["label"],
                        "tag_name": field["tag_name"],
                        "input_type": field["input_type"],
                        "role": field["role"],
                        "required": field["required"],
                        "options": [],
                    }
                    for field in fields
                ]

        if not fields and state.get("allow_apply_click"):
            apply_clicked = await self.browser.click_apply()
            state["result"]["apply_clicked"] = bool(apply_clicked)
            if apply_clicked:
                await self.send("Apply button clicked; waiting for the application form")
                await self.tools.call("wait_for_form", timeout_ms=BROWSER_STEP_WAIT_TIMEOUT_MS)
                snapshot_result = await self.tools.call("snapshot_form")
                page_result = await self.tools.call("read_page")
                fields = list(snapshot_result.data or []) if snapshot_result.success else []
                browser_snapshot = page_result.data or {}

        if not fields:
            await self.browser.scroll_for_form_fields()
            snapshot_result = await self.tools.call("snapshot_form")
            page_result = await self.tools.call("read_page")
            fields = list(snapshot_result.data or []) if snapshot_result.success else []
            browser_snapshot = page_result.data or {}

        return fields, browser_snapshot

    async def read_page(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("stop_reason"):
            return await self._persist(state)
        await self._preprocess_page()
        await self._handle_auth_gate(state)
        fields, browser_snapshot = await self._read_fields(state)
        state["fields"] = fields
        state["browser_snapshot"] = browser_snapshot
        state["result"]["url"] = browser_snapshot.get("url") or state["job_url"]
        state["result"]["browser_mode"] = getattr(self.browser, "mode", "unknown")
        if fields and state.get("count_step"):
            state["current_step"] += 1
            state["result"]["steps_processed"] = state["current_step"]
            state["result"]["fields_detected"] += len(fields)
            state["count_step"] = False
            await self.send(f"Processing form step {state['current_step']} ({len(fields)} fields)")
        if not fields:
            state["stop_reason"] = "no_fields_detected"
            state["result"]["stopped_reason"] = "no_fields_detected"
            await self.send("No application fields detected after scrolling and apply attempts")
        return await self._persist(state)

    async def plan_fields(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("stop_reason"):
            return await self._persist(state)

        state["field_plan"] = []
        for field in state.get("fields") or []:
            label = str(field.get("label") or "").strip()
            field_type = classify(label)
            state["field_plan"].append(
                {
                    **field,
                    "field_type": field_type,
                }
            )
            await self.send(f"Detected field: {label}")
        return await self._persist(state)

    async def retrieve_profile_context(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("stop_reason"):
            return await self._persist(state)

        state["resolved_values"] = []
        state["knowledge_hits"] = []
        for field in state.get("field_plan") or []:
            resolution = resolve_field(
                field["field_type"],
                str(field.get("label") or ""),
                profile_id=state["profile_id"],
            )
            state["resolved_values"].append({**field, **resolution, "filled": False})
            knowledge_hits = list(resolution.get("knowledge_hits") or [])
            if knowledge_hits:
                state["knowledge_hits"].extend(knowledge_hits)
        return await self._persist(state)

    async def fill_fields(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("stop_reason"):
            return await self._persist(state)

        for resolved in state.get("resolved_values") or []:
            if resolved.get("filled") or resolved.get("value") in (None, ""):
                continue

            field_type = resolved.get("field_type")
            value = resolved.get("value")
            if field_type == "resume":
                result = await self.tools.call("upload_resume", path_like=value)
                resolved["filled"] = result.success
                if result.success:
                    state["result"]["resume_uploaded"] = True
                    await self.send("Resume uploaded; waiting for the form to update")
                    await self.tools.call("wait_for_form", timeout_ms=BROWSER_STEP_WAIT_TIMEOUT_MS)
            elif field_type == "cover_letter":
                result = await self.tools.call("upload_cover_letter", path_like=value)
                resolved["filled"] = result.success
                if result.success:
                    state["result"]["cover_letter_uploaded"] = True
                    await self.send("Cover letter uploaded; waiting for the form to update")
                    await self.tools.call("wait_for_form", timeout_ms=BROWSER_STEP_WAIT_TIMEOUT_MS)
            else:
                tool_name = "select_option" if resolved.get("tag_name") == "select" or resolved.get("options") else "fill_text"
                result = await self.tools.call(tool_name, field_or_element=resolved, value=value)
                resolved["filled"] = result.success

            if resolved.get("filled"):
                state["result"]["fields_filled"] += 1
            else:
                resolved["fill_error"] = "tool_failed"
        return await self._persist(state)

    async def evaluate_page(self, state: dict[str, Any]) -> dict[str, Any]:
        page_result = await self.tools.call("read_page")
        if page_result.success and isinstance(page_result.data, dict):
            state["browser_snapshot"] = page_result.data
        return await self._persist(state)

    async def assess_gaps(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("stop_reason") == "no_fields_detected":
            return await self._persist(state)

        pending_questions: list[HumanEscalation] = []
        for resolved in state.get("resolved_values") or []:
            value = resolved.get("value")
            confidence = float(resolved.get("confidence") or 0.0)
            needs_value = value in (None, "")
            low_confidence = not needs_value and confidence < 0.6
            fill_failed = bool(value) and not resolved.get("filled")
            should_pause = low_confidence or fill_failed or (resolved.get("required") and needs_value)
            if not should_pause:
                continue

            reason = "missing_value"
            if low_confidence:
                reason = "low_confidence"
            elif fill_failed:
                reason = "fill_failed"

            pending_questions.append(
                HumanEscalation(
                    field_id=str(resolved.get("field_id") or ""),
                    label=str(resolved.get("label") or ""),
                    field_type=str(resolved.get("field_type") or "unknown"),
                    reason=reason,
                    confidence=confidence,
                    retry_count=state.get("retry_count", 0),
                )
            )

        state["pending_questions"] = pending_questions
        if pending_questions:
            await self.send(
                "Some fields still need review",
                event_type="status",
                pending_questions=[question.model_dump() for question in pending_questions],
            )
        return await self._persist(state)

    async def human_pause(self, state: dict[str, Any]) -> dict[str, Any]:
        if not state.get("pending_questions"):
            return await self._persist(state)

        question = state["pending_questions"][0]
        question_payload = question.model_dump()
        await self.send(
            question.label,
            event_type="question",
            field=question.label,
            question=question_payload,
            application_id=state["application_id"],
        )

        if self.websocket is None:
            state["stop_reason"] = "human_input_required"
            state["result"]["stopped_reason"] = "human_input_required"
            return await self._persist(state)

        try:
            response = await self.websocket.receive_json()
        except Exception:
            response = {}

        answer = str((response or {}).get("answer") or "").strip()
        if not answer:
            state["stop_reason"] = "human_input_required"
            state["result"]["stopped_reason"] = "human_input_required"
            return await self._persist(state)

        for resolved in state.get("resolved_values") or []:
            if str(resolved.get("field_id") or "") != question.field_id:
                continue
            resolved["value"] = answer
            resolved["source"] = "human_input"
            resolved["confidence"] = 1.0
            resolved["knowledge_hits"] = []
            break

        store_answer(question.label, answer, profile_id=state["profile_id"])
        state["result"]["questions_asked"] += 1
        state["retry_count"] += 1
        state["pending_questions"] = state["pending_questions"][1:]
        state["stop_reason"] = None
        state["result"]["stopped_reason"] = None
        return await self._persist(state)

    async def advance_or_submit(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("stop_reason"):
            state["continue_loop"] = False
            return await self._persist(state)

        next_result = await self.tools.call("click_next")
        if next_result.success:
            state["result"]["steps_advanced"] += 1
            await self.send("Next button clicked; waiting for next form step")
            await self.tools.call("wait_for_form", timeout_ms=BROWSER_STEP_WAIT_TIMEOUT_MS)
            state["continue_loop"] = True
            state["allow_apply_click"] = False
            state["count_step"] = True
            state["fields"] = []
            state["field_plan"] = []
            state["resolved_values"] = []
            state["pending_questions"] = []
            return await self._persist(state)

        if self.auto_submit:
            await self.send("Submitting application")
            submit_result = await self.tools.call("click_submit")
            state["submitted"] = submit_result.success
            state["result"]["submitted"] = submit_result.success
        else:
            await self.send("Auto-submit disabled; form left open for review")
        state["continue_loop"] = False
        return await self._persist(state)
