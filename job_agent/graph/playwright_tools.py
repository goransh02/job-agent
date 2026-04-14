from __future__ import annotations

from typing import Any, Awaitable, Callable

from job_agent.graph.types import ToolCallResult


ToolCallable = Callable[..., Awaitable[Any]]


PLAYWRIGHT_TOOL_DEFINITIONS = [
    {
        "name": "open_job",
        "description": "Open a job application URL in the browser.",
    },
    {
        "name": "snapshot_form",
        "description": "Return the current detected form fields with browser element handles for filling.",
    },
    {
        "name": "read_page",
        "description": "Return a serializable page summary including fields and visible errors.",
    },
    {
        "name": "fill_text",
        "description": "Fill a text-like field with the provided value.",
    },
    {
        "name": "select_option",
        "description": "Select or choose a value for a select or combobox field.",
    },
    {
        "name": "upload_resume",
        "description": "Upload the stored resume file to the page.",
    },
    {
        "name": "upload_cover_letter",
        "description": "Upload the stored cover letter file to the page.",
    },
    {
        "name": "click_next",
        "description": "Advance the application to the next step.",
    },
    {
        "name": "click_submit",
        "description": "Submit the current application form.",
    },
    {
        "name": "wait_for_form",
        "description": "Wait for the next application step or upload controls to be ready.",
    },
]


class PlaywrightToolRegistry:
    def __init__(self, browser) -> None:
        self.browser = browser
        self._tools: dict[str, ToolCallable] = {
            "open_job": self.browser.open_job,
            "snapshot_form": self.browser.snapshot_form,
            "read_page": self.browser.read_page,
            "fill_text": self.browser.fill_text,
            "select_option": self.browser.select_option,
            "upload_resume": self.browser.upload_resume,
            "upload_cover_letter": self.browser.upload_cover_letter,
            "click_next": self.browser.click_next,
            "click_submit": self.browser.click_submit,
            "wait_for_form": self.browser.wait_for_form_ready,
        }

    @property
    def tool_definitions(self) -> list[dict[str, str]]:
        return list(PLAYWRIGHT_TOOL_DEFINITIONS)

    async def call(self, tool_name: str, **kwargs) -> ToolCallResult:
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolCallResult(tool_name=tool_name, success=False, error="Unknown tool")

        try:
            data = await tool(**kwargs)
        except TypeError:
            try:
                data = await tool(*kwargs.values())
            except Exception as exc:
                return ToolCallResult(tool_name=tool_name, success=False, error=str(exc))
        except Exception as exc:
            return ToolCallResult(tool_name=tool_name, success=False, error=str(exc))

        success = True
        if isinstance(data, bool):
            success = data
        return ToolCallResult(tool_name=tool_name, success=success, data=data)
