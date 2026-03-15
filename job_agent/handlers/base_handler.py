from __future__ import annotations

from job_agent.agent.cookie_handler import accept_cookies
from job_agent.agent.field_classifier import classify
from job_agent.agent.form_parser import parse_fields
from job_agent.agent.learning_engine import store_answer
from job_agent.agent.value_resolver import resolve
from job_agent.browser.playwright_browser import Browser
from job_agent.config import AUTO_SUBMIT


class BaseHandler:
    platform_name = "generic"

    def __init__(self, websocket=None, browser=None, auto_submit: bool | None = None):
        self.websocket = websocket
        self.browser = browser or Browser()
        self.auto_submit = AUTO_SUBMIT if auto_submit is None else auto_submit

    async def send(self, message: str, event_type: str = "status", **payload) -> None:
        if self.websocket is None:
            return

        body = {"type": event_type, "message": message}
        body.update(payload)
        await self.websocket.send_json(body)

    async def ask(self, field: str) -> str | None:
        if self.websocket is None:
            return None

        await self.websocket.send_json({"type": "question", "field": field})
        data = await self.websocket.receive_json()
        return (data or {}).get("answer")

    def preprocess_page(self) -> None:
        try:
            accept_cookies(self.browser.page)
        except Exception:
            return

    def get_fields(self):
        return parse_fields(self.browser.page)

    async def apply(self, url: str) -> dict[str, object]:
        result = {
            "platform": self.platform_name,
            "url": url,
            "fields_detected": 0,
            "fields_filled": 0,
            "questions_asked": 0,
            "submitted": False,
        }

        await self.send(f"Opening {self.platform_name} job page")
        self.browser.open(url)
        self.preprocess_page()

        fields = self.get_fields()
        result["fields_detected"] = len(fields)

        for field in fields:
            label = field["label"]
            element = field["element"]

            await self.send(f"Detected field: {label}")

            field_type = classify(label)
            value = resolve(field_type, label)

            if value in (None, ""):
                value = await self.ask(label)
                if value not in (None, ""):
                    result["questions_asked"] += 1
                    store_answer(label, value)

            if value in (None, ""):
                continue

            if self.browser.fill(element, value):
                result["fields_filled"] += 1

        if self.auto_submit:
            await self.send("Submitting application")
            result["submitted"] = self.browser.click_submit()
        else:
            await self.send("Auto-submit disabled; form left open for review")

        return result
