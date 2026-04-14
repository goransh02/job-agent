from __future__ import annotations

import logging
from typing import Iterable

from job_agent.agent.cookie_handler import accept_cookies
from job_agent.agent.field_classifier import classify
from job_agent.agent.form_parser import parse_fields
from job_agent.agent.learning_engine import store_answer
from job_agent.agent.login_handler import attempt_login
from job_agent.agent.register_handler import attempt_register
from job_agent.agent.value_resolver import resolve
from job_agent.browser.playwright_browser import Browser
from job_agent.config import AUTO_SUBMIT, BROWSER_STEP_WAIT_TIMEOUT_MS, MAX_FORM_STEPS
from job_agent.logging_utils import trace

logger = logging.getLogger(__name__)


class BaseHandler:
    platform_name = "generic"

    def __init__(
        self,
        websocket=None,
        browser=None,
        auto_submit: bool | None = None,
        profile_id: str | None = None,
    ):
        self.websocket = websocket
        self.browser = browser or Browser()
        self.auto_submit = AUTO_SUBMIT if auto_submit is None else auto_submit
        self.profile_id = profile_id

    def _build_result(self, url: str, *, continued: bool = False) -> dict[str, object]:
        return {
            "platform": self.platform_name,
            "profile_id": self.profile_id,
            "url": url,
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
        }

    async def send(self, message: str, event_type: str = "status", **payload) -> None:
        if self.websocket is None:
            return

        body = {"type": event_type, "message": message}
        body.update(payload)
        await self.websocket.send_json(body)

    async def ask(self, field: str) -> str | None:
        if self.websocket is None:
            logger.info("No websocket available to ask for field '%s'", field)
            return None

        logger.info("Prompting client for field '%s'", field)
        await self.websocket.send_json({"type": "question", "field": field})
        data = await self.websocket.receive_json()
        logger.info("Received client answer for field '%s': %s", field, bool((data or {}).get("answer")))
        return (data or {}).get("answer")

    async def preprocess_page(self) -> None:
        try:
            accepted = await accept_cookies(self.browser.page)
            logger.info("Cookie banner handled: %s", accepted)
        except Exception:
            logger.exception("Cookie handling failed")
            return

    async def get_fields(self):
        fields = await parse_fields(self.browser.page)
        logger.info("Parsed %s candidate fields", len(fields))
        return fields

    def _field_signature(self, fields: Iterable[dict[str, object]]) -> tuple[str, ...]:
        return tuple(sorted(str(field.get("label", "")).strip().lower() for field in fields))

    def _step_marker(self, fields: list[dict[str, object]]) -> tuple[str, tuple[str, ...]]:
        current_url = ""
        if getattr(self.browser, "page", None) is not None:
            current_url = getattr(self.browser.page, "url", "") or ""
        return (current_url, self._field_signature(fields))

    async def _fill_fields(
        self,
        fields: list[dict[str, object]],
        result: dict[str, object],
    ) -> None:
        for field in fields:
            label = field["label"]
            element = field["element"]

            logger.info("Processing field '%s'", label)
            await self.send(f"Detected field: {label}")

            field_type = classify(label)
            logger.info("Classified field '%s' as '%s'", label, field_type)
            value = resolve(field_type, label, profile_id=self.profile_id)
            logger.info("Resolved value for field '%s': %s", label, value is not None and value != "")

            if value in (None, ""):
                value = await self.ask(label)
                if value not in (None, ""):
                    result["questions_asked"] += 1
                    logger.info("Storing learned answer for field '%s'", label)
                    store_answer(label, value, profile_id=self.profile_id)

            if value in (None, ""):
                logger.warning("Skipping field '%s' because no value is available", label)
                continue

            if await self.browser.fill(field, value):
                result["fields_filled"] += 1
                logger.info("Filled field '%s'", label)
            else:
                logger.warning("Failed to fill field '%s'", label)

    async def _try_document_upload(
        self,
        result: dict[str, object],
        *,
        field_type: str,
        document_type: str,
        label: str,
        result_key: str,
        upload_method_name: str,
    ) -> bool:
        if result.get(result_key):
            return False

        if not await self.browser.has_document_upload_controls(document_type):
            return False

        document_path = resolve(field_type, label, profile_id=self.profile_id)
        if not document_path:
            logger.info("No stored %s available for auto-upload", document_type)
            return False

        await self.send(f"Attempting {label.lower()} upload from stored profile")
        upload_method = getattr(self.browser, upload_method_name)
        if not await upload_method(document_path):
            logger.info("%s upload controls were not usable on the current page", document_type)
            return False

        result[result_key] = True
        await self.send(f"{label} uploaded; waiting for the form to update")
        await self.browser.wait_for_form_ready(timeout_ms=BROWSER_STEP_WAIT_TIMEOUT_MS)
        return True

    async def _try_document_uploads(self, result: dict[str, object]) -> list[dict[str, object]] | None:
        uploaded_any = False

        uploaded_any = await self._try_document_upload(
            result,
            field_type="resume",
            document_type="resume",
            label="Resume/CV",
            result_key="resume_uploaded",
            upload_method_name="upload_resume",
        ) or uploaded_any

        uploaded_any = await self._try_document_upload(
            result,
            field_type="cover_letter",
            document_type="cover_letter",
            label="Cover Letter",
            result_key="cover_letter_uploaded",
            upload_method_name="upload_cover_letter",
        ) or uploaded_any

        if not uploaded_any:
            return None

        await self.preprocess_page()
        return await self.get_fields()

    async def _try_auth_gate(self, result: dict[str, object]) -> list[dict[str, object]] | None:
        if result.get("auth_gate_handled"):
            return None

        if not await self.browser.has_auth_gate():
            return None

        result["auth_gate_handled"] = True
        await self.send("Account gate detected; attempting to continue the application flow")

        if await self.browser.click_create_account():
            await self.send("Create Account clicked; waiting for registration form")
            await self.browser.wait_for_form_ready(timeout_ms=BROWSER_STEP_WAIT_TIMEOUT_MS)
            await self.preprocess_page()

        if await attempt_register(self.browser.page, profile_id=self.profile_id):
            await self.send("Registration form credentials filled; checking the page again")
        elif await attempt_login(self.browser.page, profile_id=self.profile_id):
            await self.send("Login form credentials filled; checking the page again")
        else:
            await self.send("Account gate requires manual review; use Play / Resume after intervention")
            return []

        await self.browser.wait_for_form_ready(timeout_ms=BROWSER_STEP_WAIT_TIMEOUT_MS)
        await self.preprocess_page()
        return await self.get_fields()

    async def _collect_fields_with_recovery(
        self,
        result: dict[str, object],
        *,
        allow_apply_click: bool,
    ) -> list[dict[str, object]]:
        await self.preprocess_page()

        auth_fields = await self._try_auth_gate(result)
        if auth_fields is not None:
            fields = auth_fields
        else:
            fields = await self.get_fields()

        if not fields:
            uploaded_fields = await self._try_document_uploads(result)
            if uploaded_fields is not None:
                fields = uploaded_fields

        if not fields:
            await self.send("No fields detected yet; scrolling to load more of the page")
            if await self.browser.scroll_for_form_fields():
                await self.preprocess_page()
                fields = await self.get_fields()

        if not fields and allow_apply_click:
            trace(logger, "No fields detected on landing page; attempting to click apply")
            await self.send("No form fields detected; looking for Apply button")
            result["apply_clicked"] = await self.browser.click_apply()

            if result["apply_clicked"]:
                await self.send("Apply button clicked; waiting for application form")
                await self.browser.wait_for_form_ready()
                await self.preprocess_page()
                auth_fields = await self._try_auth_gate(result)
                if auth_fields is not None:
                    fields = auth_fields
                else:
                    fields = await self.get_fields()
                if not fields:
                    uploaded_fields = await self._try_document_uploads(result)
                    if uploaded_fields is not None:
                        fields = uploaded_fields
                if not fields:
                    await self.send("Form still not visible; scrolling to reveal loaded fields")
                    if await self.browser.scroll_for_form_fields():
                        await self.preprocess_page()
                        fields = await self.get_fields()
            else:
                trace(logger, "No apply button was clicked; proceeding with current page")

        return fields

    async def _process_current_page(
        self,
        result: dict[str, object],
        *,
        allow_apply_click: bool,
    ) -> dict[str, object]:
        fields = await self._collect_fields_with_recovery(
            result,
            allow_apply_click=allow_apply_click,
        )

        if not (current_fields := fields):
            trace(logger, "No form fields detected after scrolling/apply attempts; stopping run")
            result["stopped_reason"] = "no_fields_detected"
            await self.send("No application fields detected after scrolling and apply attempts")
            logger.warning("Stopping handler because no application fields were detected")
            return result

        previous_marker = None

        for step_number in range(1, MAX_FORM_STEPS + 1):
            current_marker = self._step_marker(current_fields)
            if previous_marker is not None and current_marker == previous_marker:
                trace(logger, "Form did not advance after clicking next; stopping at step %s", step_number)
                break

            result["steps_processed"] = step_number
            result["fields_detected"] += len(current_fields)
            trace(
                logger,
                "Processing form step %s with %s fields",
                step_number,
                len(current_fields),
            )
            await self.send(
                f"Processing form step {step_number} ({len(current_fields)} fields)",
            )
            await self._fill_fields(current_fields, result)
            refreshed_fields = await self._try_document_uploads(result)
            if refreshed_fields is not None:
                refreshed_marker = self._step_marker(refreshed_fields)
                if refreshed_marker != current_marker:
                    await self.send("Form updated after document upload; checking for additional fields")
                    await self._fill_fields(refreshed_fields, result)
                    current_fields = refreshed_fields
                    current_marker = refreshed_marker

            previous_marker = current_marker
            next_clicked = await self.browser.click_next()
            if not next_clicked:
                trace(logger, "No next button found after step %s", step_number)
                break

            result["steps_advanced"] += 1
            await self.send("Next button clicked; waiting for next form step")
            await self.browser.wait_for_form_ready(timeout_ms=BROWSER_STEP_WAIT_TIMEOUT_MS)
            current_fields = await self._collect_fields_with_recovery(
                result,
                allow_apply_click=False,
            )
            if not current_fields:
                result["stopped_reason"] = "no_fields_after_next"
                await self.send(
                    "No fields detected after next; review the open browser and use Continue Detection",
                )
                logger.warning("Stopping after next because no fields were detected on the advanced step")
                break
        else:
            trace(logger, "Reached maximum configured form steps (%s)", MAX_FORM_STEPS)

        if result["stopped_reason"] is not None:
            await self.send("Run paused; review the open browser and use Continue Detection if needed")
            logger.info("Run paused with stopped_reason=%s", result["stopped_reason"])
        elif self.auto_submit:
            await self.send("Submitting application")
            result["submitted"] = await self.browser.click_submit()
            logger.info("Submit attempted: %s", result["submitted"])
        else:
            await self.send("Auto-submit disabled; form left open for review")
            logger.info("Auto-submit disabled; leaving form open")

        logger.info("Handler result: %s", result)
        return result

    async def apply(self, url: str) -> dict[str, object]:
        result = self._build_result(url)

        trace(logger, "Handler %s opening URL %s", self.platform_name, url)
        await self.send(
            f"Launching browser (headless={self.browser.headless})",
        )
        await self.send(
            f"Browser mode: {getattr(self.browser, 'mode', 'unknown')}",
        )
        await self.send(f"Opening {self.platform_name} job page")
        await self.browser.open(url)
        return await self._process_current_page(result, allow_apply_click=True)

    async def continue_apply(self) -> dict[str, object]:
        if getattr(self.browser, "page", None) is None:
            raise RuntimeError("No active browser session to continue")

        current_url = getattr(self.browser.page, "url", "") or ""
        result = self._build_result(current_url, continued=True)
        trace(logger, "Continuing handler %s on current page %s", self.platform_name, current_url)
        await self.send(f"Browser mode: {getattr(self.browser, 'mode', 'unknown')}")
        await self.send("Continuing form detection on the current page")
        return await self._process_current_page(result, allow_apply_click=False)
