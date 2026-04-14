import unittest
from unittest.mock import patch

from job_agent.graph.runner import ApplicationGraphRunner


class FakeWebSocket:
    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.sent_messages = []

    async def send_json(self, payload):
        self.sent_messages.append(payload)

    async def receive_json(self):
        answer = self.answers.pop(0) if self.answers else None
        return {"answer": answer}


class FakePage:
    def __init__(self, url=""):
        self.url = url


class FakeGraphBrowser:
    def __init__(self, steps):
        self.steps = steps
        self.current_step = 0
        self.page = FakePage()
        self.mode = "test"
        self.headless = False
        self.opened_urls = []
        self.filled_values = []
        self.uploads = []
        self.submitted = False

    async def open_job(self, url):
        self.page.url = url
        self.opened_urls.append(url)
        return True

    async def snapshot_form(self):
        fields = []
        for index, field in enumerate(self.steps[self.current_step]):
            payload = dict(field)
            payload.setdefault("field_id", f"field-{self.current_step}-{index}")
            payload.setdefault("required", True)
            payload.setdefault("options", [])
            fields.append(payload)
        return fields

    async def read_page(self):
        fields = await self.snapshot_form()
        return {
            "url": self.page.url,
            "field_count": len(fields),
            "fields": [
                {
                    "field_id": field["field_id"],
                    "label": field["label"],
                    "tag_name": field["tag_name"],
                    "input_type": field["input_type"],
                    "role": field["role"],
                    "required": field["required"],
                    "options": field["options"],
                }
                for field in fields
            ],
            "errors": [],
        }

    async def fill_text(self, field_or_element, value):
        self.filled_values.append((field_or_element["label"], value))
        return True

    async def select_option(self, field_or_element, value):
        self.filled_values.append((field_or_element["label"], value))
        return True

    async def upload_resume(self, path_like):
        self.uploads.append(("resume", path_like))
        return True

    async def upload_cover_letter(self, path_like):
        self.uploads.append(("cover_letter", path_like))
        return True

    async def click_next(self):
        if self.current_step >= len(self.steps) - 1:
            return False
        self.current_step += 1
        return True

    async def click_submit(self):
        self.submitted = True
        return True

    async def wait_for_form_ready(self, timeout_ms=None):
        return True

    async def click_apply(self):
        return False

    async def scroll_for_form_fields(self, max_scrolls=4):
        return False

    async def has_document_upload_controls(self, document_type="resume"):
        return False

    async def has_auth_gate(self):
        return False

    async def click_create_account(self):
        return False


class ApplicationGraphRunnerTests(unittest.IsolatedAsyncioTestCase):
    @patch("job_agent.graph.runner.accept_cookies", return_value=True)
    @patch("job_agent.graph.runner.attempt_register", return_value=False)
    @patch("job_agent.graph.runner.attempt_login", return_value=False)
    async def test_runner_processes_multi_step_form(self, *_mocks):
        browser = FakeGraphBrowser(
            steps=[
                [
                    {
                        "label": "First Name",
                        "tag_name": "input",
                        "input_type": "text",
                        "role": "",
                        "element": object(),
                    }
                ],
                [
                    {
                        "label": "Country",
                        "tag_name": "select",
                        "input_type": "",
                        "role": "",
                        "options": ["India +91"],
                        "element": object(),
                    }
                ],
            ]
        )
        runner = ApplicationGraphRunner(platform="generic", browser=browser, auto_submit=False)
        state = runner.build_initial_state(job_url="https://example.com/job", profile_id="candidate-a")

        with patch(
            "job_agent.graph.runner.resolve_field",
            side_effect=[
                {"value": "Goran", "source": "profile", "confidence": 1.0, "knowledge_hits": []},
                {"value": "India +91", "source": "profile", "confidence": 1.0, "knowledge_hits": []},
            ],
        ):
            result = await runner.run(state)

        self.assertEqual(browser.opened_urls, ["https://example.com/job"])
        self.assertEqual(browser.filled_values, [("First Name", "Goran"), ("Country", "India +91")])
        self.assertEqual(result["steps_processed"], 2)
        self.assertEqual(result["steps_advanced"], 1)
        self.assertFalse(result["submitted"])

    @patch("job_agent.graph.runner.accept_cookies", return_value=True)
    @patch("job_agent.graph.runner.attempt_register", return_value=False)
    @patch("job_agent.graph.runner.attempt_login", return_value=False)
    async def test_runner_requests_human_input_and_resumes_fill(self, *_mocks):
        browser = FakeGraphBrowser(
            steps=[
                [
                    {
                        "label": "Custom Question",
                        "tag_name": "input",
                        "input_type": "text",
                        "role": "",
                        "element": object(),
                    }
                ]
            ]
        )
        websocket = FakeWebSocket(answers=["Manual answer"])
        runner = ApplicationGraphRunner(
            platform="generic",
            websocket=websocket,
            browser=browser,
            auto_submit=False,
        )
        state = runner.build_initial_state(job_url="https://example.com/job", profile_id="candidate-a")

        with patch(
            "job_agent.graph.runner.resolve_field",
            return_value={"value": None, "source": "none", "confidence": 0.0, "knowledge_hits": []},
        ), patch("job_agent.graph.runner.store_answer") as store_answer:
            result = await runner.run(state)

        self.assertEqual(browser.filled_values, [("Custom Question", "Manual answer")])
        self.assertEqual(result["questions_asked"], 1)
        self.assertEqual(result["pending_questions"], [])
        store_answer.assert_called_once_with("Custom Question", "Manual answer", profile_id="candidate-a")
        self.assertTrue(any(message["type"] == "question" for message in websocket.sent_messages))
