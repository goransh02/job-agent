from __future__ import annotations

import logging

from job_agent.agent.platform_detector import detect_platform
from job_agent.graph.runner import ApplicationGraphRunner
from job_agent.logging_utils import trace
from job_agent.services.application_service import load_application_state
from job_agent.services.profile_service import normalize_profile_id

logger = logging.getLogger(__name__)


class JobAgent:
    def __init__(self, handler_map=None):
        self.handler_map = handler_map or {}
        self.active_runner: ApplicationGraphRunner | None = None
        self.active_application_id: str | None = None
        self.active_profile_id: str = normalize_profile_id()

    async def run(
        self,
        url: str,
        websocket=None,
        browser=None,
        *,
        profile_id: str | None = None,
    ):
        platform = detect_platform(url)
        trace(logger, "Resolved platform '%s' for URL %s", platform, url)
        runner = ApplicationGraphRunner(
            platform=platform,
            websocket=websocket,
            browser=browser,
        )
        state = runner.build_initial_state(
            job_url=url,
            profile_id=profile_id,
            continued=False,
        )
        self.active_runner = runner
        self.active_application_id = state["application_id"]
        self.active_profile_id = state["profile_id"]
        await runner.send(f"Detected platform: {platform}")
        return await runner.run(state)

    async def continue_run(
        self,
        websocket=None,
        *,
        application_id: str | None = None,
        profile_id: str | None = None,
    ):
        if application_id:
            self.active_application_id = application_id
        if profile_id:
            self.active_profile_id = normalize_profile_id(profile_id)

        if self.active_runner is None or self.active_application_id is None:
            raise RuntimeError("No active application session to continue. Start an application first.")

        self.active_runner.websocket = websocket
        stored_state = load_application_state(self.active_application_id) or {}
        current_url = getattr(getattr(self.active_runner.browser, "page", None), "url", "") or stored_state.get("job_url")
        state = dict(stored_state)
        if not state:
            state = self.active_runner.build_initial_state(
                job_url=current_url or "",
                profile_id=self.active_profile_id,
                application_id=self.active_application_id,
                continued=True,
            )
        else:
            state["job_url"] = current_url or state.get("job_url") or ""
            state["continued"] = True
            state["continue_loop"] = True
            state["allow_apply_click"] = False
            state["count_step"] = True
            state["fields"] = []
            state["field_plan"] = []
            state["resolved_values"] = []
            state["browser_snapshot"] = {}
            state["pending_questions"] = []
            state["stop_reason"] = None
            state.setdefault("result", {})
            state["result"]["continued"] = True
            state["result"]["stopped_reason"] = None
            state["result"]["url"] = current_url or state["job_url"]

        await self.active_runner.send("Resuming active application session")
        return await self.active_runner.run(state)

    async def apply(
        self,
        url: str,
        websocket=None,
        browser=None,
        *,
        profile_id: str | None = None,
    ):
        return await self.run(
            url,
            websocket=websocket,
            browser=browser,
            profile_id=profile_id,
        )
