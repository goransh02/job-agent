import unittest

from job_agent.graph.playwright_tools import PlaywrightToolRegistry


class ToolBrowserStub:
    def __init__(self):
        self.calls = []

    async def open_job(self, url):
        self.calls.append(("open_job", url))
        return True

    async def snapshot_form(self):
        self.calls.append(("snapshot_form", None))
        return [{"field_id": "f1"}]

    async def read_page(self):
        self.calls.append(("read_page", None))
        return {"field_count": 1}

    async def fill_text(self, field_or_element, value):
        self.calls.append(("fill_text", value))
        return True

    async def select_option(self, field_or_element, value):
        self.calls.append(("select_option", value))
        return True

    async def upload_resume(self, path_like):
        self.calls.append(("upload_resume", path_like))
        return True

    async def upload_cover_letter(self, path_like):
        self.calls.append(("upload_cover_letter", path_like))
        return True

    async def click_next(self):
        self.calls.append(("click_next", None))
        return True

    async def click_submit(self):
        self.calls.append(("click_submit", None))
        return True

    async def wait_for_form_ready(self, timeout_ms=None):
        self.calls.append(("wait_for_form", timeout_ms))
        return True


class PlaywrightToolRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_registry_calls_each_predefined_tool(self):
        browser = ToolBrowserStub()
        registry = PlaywrightToolRegistry(browser)

        calls = [
            await registry.call("open_job", url="https://example.com/job"),
            await registry.call("snapshot_form"),
            await registry.call("read_page"),
            await registry.call("fill_text", field_or_element={"field_id": "f1"}, value="Goran"),
            await registry.call("select_option", field_or_element={"field_id": "f2"}, value="India"),
            await registry.call("upload_resume", path_like="/tmp/resume.pdf"),
            await registry.call("upload_cover_letter", path_like="/tmp/cover-letter.pdf"),
            await registry.call("click_next"),
            await registry.call("click_submit"),
            await registry.call("wait_for_form", timeout_ms=2500),
        ]

        self.assertTrue(all(call.success for call in calls))
        self.assertEqual(
            [name for name, _ in browser.calls],
            [
                "open_job",
                "snapshot_form",
                "read_page",
                "fill_text",
                "select_option",
                "upload_resume",
                "upload_cover_letter",
                "click_next",
                "click_submit",
                "wait_for_form",
            ],
        )
