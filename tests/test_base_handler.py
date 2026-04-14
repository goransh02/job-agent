import unittest
from unittest.mock import patch

from job_agent.handlers.base_handler import BaseHandler


class FakeWebSocket:
    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.sent_messages = []

    async def send_json(self, payload):
        self.sent_messages.append(payload)

    async def receive_json(self):
        answer = self.answers.pop(0) if self.answers else None
        return {"answer": answer}


class FakeBrowser:
    def __init__(
        self,
        next_click_results=None,
        upload_resume_result=False,
        upload_cover_letter_result=False,
        upload_controls=None,
        auth_gate=False,
    ):
        self.headless = False
        self.page = object()
        self.opened_urls = []
        self.filled_values = []
        self.submit_clicked = False
        self.apply_clicked = False
        self.waited_for_form = False
        self.scrolled_for_fields = False
        self.next_click_results = list(next_click_results or [])
        self.next_click_calls = 0
        self.upload_resume_result = upload_resume_result
        self.upload_cover_letter_result = upload_cover_letter_result
        self.upload_resume_calls = []
        self.upload_cover_letter_calls = []
        self.upload_controls = dict(upload_controls or {"resume": False, "cover_letter": False})
        self.auth_gate = auth_gate
        self.create_account_clicked = False

    async def open(self, url):
        self.opened_urls.append(url)

    async def click_apply(self):
        self.apply_clicked = True
        return True

    async def wait_for_form_ready(self, timeout_ms=None):
        self.waited_for_form = True
        return True

    async def scroll_for_form_fields(self, max_scrolls=4):
        self.scrolled_for_fields = True
        return False

    async def upload_resume(self, path):
        self.upload_resume_calls.append(path)
        return self.upload_resume_result

    async def upload_cover_letter(self, path):
        self.upload_cover_letter_calls.append(path)
        return self.upload_cover_letter_result

    async def has_document_upload_controls(self, document_type="resume"):
        return self.upload_controls.get(document_type, False)

    async def has_auth_gate(self):
        return self.auth_gate

    async def click_create_account(self):
        self.create_account_clicked = True
        return True

    async def click_next(self):
        self.next_click_calls += 1
        if not self.next_click_results:
            return False
        return self.next_click_results.pop(0)

    async def fill(self, element, value):
        if isinstance(element, dict):
            element = element.get("element")
        self.filled_values.append((element, value))
        return True

    async def click_submit(self):
        self.submit_clicked = True
        return True


class BaseHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_asks_user_when_value_is_unknown(self):
        browser = FakeBrowser()
        websocket = FakeWebSocket(answers=["Manual answer"])
        handler = BaseHandler(websocket=websocket, browser=browser, auto_submit=True)

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            return_value=[{"label": "Custom question", "element": "field-1"}],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            return_value="unknown",
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            return_value=None,
        ), patch(
            "job_agent.handlers.base_handler.store_answer",
        ) as store_answer:
            result = await handler.apply("https://example.com/job")

        self.assertEqual(browser.opened_urls, ["https://example.com/job"])
        self.assertEqual(browser.filled_values, [("field-1", "Manual answer")])
        self.assertTrue(browser.submit_clicked)
        self.assertEqual(result["fields_detected"], 1)
        self.assertEqual(result["fields_filled"], 1)
        self.assertEqual(result["questions_asked"], 1)
        self.assertTrue(result["submitted"])
        store_answer.assert_called_once_with("Custom question", "Manual answer", profile_id=None)

    async def test_apply_passes_profile_id_to_resolver_and_learning(self):
        browser = FakeBrowser()
        websocket = FakeWebSocket(answers=["Manual answer"])
        handler = BaseHandler(
            websocket=websocket,
            browser=browser,
            auto_submit=False,
            profile_id="candidate-a",
        )

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            return_value=[{"label": "Custom question", "element": "field-1"}],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            return_value="unknown",
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            return_value=None,
        ) as resolve, patch(
            "job_agent.handlers.base_handler.store_answer",
        ) as store_answer:
            await handler.apply("https://example.com/job")

        resolve.assert_called_once_with("unknown", "Custom question", profile_id="candidate-a")
        store_answer.assert_called_once_with("Custom question", "Manual answer", profile_id="candidate-a")

    async def test_apply_skips_submit_when_auto_submit_is_disabled(self):
        browser = FakeBrowser()
        handler = BaseHandler(websocket=None, browser=browser, auto_submit=False)

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            return_value=[{"label": "First name", "element": "field-1"}],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            return_value="first_name",
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            return_value="Goran",
        ):
            result = await handler.apply("https://example.com/job")

        self.assertEqual(browser.filled_values, [("field-1", "Goran")])
        self.assertFalse(browser.submit_clicked)
        self.assertFalse(result["submitted"])

    async def test_apply_clicks_apply_button_before_parsing_form(self):
        browser = FakeBrowser()
        handler = BaseHandler(websocket=None, browser=browser, auto_submit=False)

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            side_effect=[
                [],
                [{"label": "First name", "element": "field-1"}],
            ],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            return_value="first_name",
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            return_value="Goran",
        ):
            result = await handler.apply("https://example.com/job")

        self.assertTrue(browser.apply_clicked)
        self.assertTrue(browser.scrolled_for_fields)
        self.assertTrue(browser.waited_for_form)
        self.assertEqual(browser.filled_values, [("field-1", "Goran")])
        self.assertTrue(result["apply_clicked"])
        self.assertEqual(result["fields_detected"], 1)

    async def test_apply_handles_multi_step_forms_with_next(self):
        browser = FakeBrowser(next_click_results=[True, False])
        handler = BaseHandler(websocket=None, browser=browser, auto_submit=False)

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            side_effect=[
                [{"label": "First name", "element": "field-1"}],
                [{"label": "Last name", "element": "field-2"}],
            ],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            side_effect=["first_name", "last_name"],
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            side_effect=["Goran", "Ghattani"],
        ):
            result = await handler.apply("https://example.com/job")

        self.assertEqual(
            browser.filled_values,
            [("field-1", "Goran"), ("field-2", "Ghattani")],
        )
        self.assertEqual(browser.next_click_calls, 2)
        self.assertEqual(result["steps_processed"], 2)
        self.assertEqual(result["steps_advanced"], 1)
        self.assertEqual(result["fields_detected"], 2)

    async def test_apply_stops_cleanly_when_no_fields_are_detected(self):
        browser = FakeBrowser()
        handler = BaseHandler(websocket=None, browser=browser, auto_submit=False)

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            return_value=[],
        ):
            result = await handler.apply("https://example.com/job")

        self.assertTrue(browser.apply_clicked)
        self.assertTrue(browser.scrolled_for_fields)
        self.assertEqual(result["fields_detected"], 0)
        self.assertEqual(result["steps_processed"], 0)
        self.assertEqual(result["stopped_reason"], "no_fields_detected")
        self.assertEqual(browser.next_click_calls, 0)
        self.assertFalse(browser.submit_clicked)

    async def test_apply_attempts_resume_upload_before_stopping(self):
        browser = FakeBrowser(
            upload_resume_result=True,
            upload_controls={"resume": True, "cover_letter": False},
        )
        handler = BaseHandler(websocket=None, browser=browser, auto_submit=False)

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            side_effect=[
                [],
                [{"label": "First name", "element": "field-1"}],
            ],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            return_value="first_name",
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            side_effect=["/tmp/resume.pdf", "Goran"],
        ):
            result = await handler.apply("https://example.com/job")

        self.assertEqual(browser.upload_resume_calls, ["/tmp/resume.pdf"])
        self.assertTrue(result["resume_uploaded"])
        self.assertEqual(browser.filled_values, [("field-1", "Goran")])

    async def test_apply_pauses_when_no_fields_are_detected_after_next(self):
        browser = FakeBrowser(next_click_results=[True])
        handler = BaseHandler(websocket=None, browser=browser, auto_submit=False)

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            side_effect=[
                [{"label": "First name", "element": "field-1"}],
                [],
            ],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            return_value="first_name",
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            side_effect=["Goran", None],
        ):
            result = await handler.apply("https://example.com/job")

        self.assertEqual(result["stopped_reason"], "no_fields_after_next")
        self.assertTrue(result["can_continue"])
        self.assertEqual(result["steps_advanced"], 1)
        self.assertFalse(result["submitted"])

    async def test_apply_attempts_resume_upload_after_next(self):
        browser = FakeBrowser(
            next_click_results=[True, False],
            upload_resume_result=True,
            upload_controls={"resume": True, "cover_letter": False},
        )
        handler = BaseHandler(websocket=None, browser=browser, auto_submit=False)

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            side_effect=[
                [{"label": "First name", "element": "field-1"}],
                [],
                [{"label": "Last name", "element": "field-2"}],
            ],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            side_effect=["first_name", "last_name"],
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            side_effect=["Goran", "/tmp/resume.pdf", "Ghattani"],
        ):
            result = await handler.apply("https://example.com/job")

        self.assertEqual(browser.upload_resume_calls, ["/tmp/resume.pdf"])
        self.assertTrue(result["resume_uploaded"])
        self.assertEqual(
            browser.filled_values,
            [("field-1", "Goran"), ("field-2", "Ghattani")],
        )
        self.assertEqual(result["steps_processed"], 2)
        self.assertEqual(result["steps_advanced"], 1)

    async def test_apply_uploads_cover_letter_on_mixed_step(self):
        browser = FakeBrowser(
            upload_resume_result=True,
            upload_cover_letter_result=True,
            upload_controls={"resume": True, "cover_letter": True},
        )
        handler = BaseHandler(websocket=None, browser=browser, auto_submit=False)

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            return_value=[{"label": "First name", "element": "field-1"}],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            return_value="first_name",
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            side_effect=["Goran", "/tmp/resume.pdf", "/tmp/cover-letter.pdf"],
        ):
            result = await handler.apply("https://example.com/job")

        self.assertEqual(browser.upload_resume_calls, ["/tmp/resume.pdf"])
        self.assertEqual(browser.upload_cover_letter_calls, ["/tmp/cover-letter.pdf"])
        self.assertTrue(result["resume_uploaded"])
        self.assertTrue(result["cover_letter_uploaded"])

    async def test_apply_handles_auth_gate_before_form_detection(self):
        browser = FakeBrowser(auth_gate=True)
        handler = BaseHandler(websocket=None, browser=browser, auto_submit=False, profile_id="candidate-a")

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.attempt_register",
            return_value=True,
        ) as attempt_register, patch(
            "job_agent.handlers.base_handler.attempt_login",
            return_value=False,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            return_value=[{"label": "First name", "element": "field-1"}],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            return_value="first_name",
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            return_value="Goran",
        ):
            result = await handler.apply("https://example.com/job")

        self.assertTrue(browser.create_account_clicked)
        self.assertTrue(result["auth_gate_handled"])
        self.assertEqual(browser.filled_values, [("field-1", "Goran")])
        attempt_register.assert_called_once_with(browser.page, profile_id="candidate-a")

    async def test_continue_apply_resumes_from_existing_page(self):
        browser = FakeBrowser()
        handler = BaseHandler(websocket=None, browser=browser, auto_submit=False)

        with patch(
            "job_agent.handlers.base_handler.accept_cookies",
            return_value=True,
        ), patch(
            "job_agent.handlers.base_handler.parse_fields",
            return_value=[{"label": "First name", "element": "field-1"}],
        ), patch(
            "job_agent.handlers.base_handler.classify",
            return_value="first_name",
        ), patch(
            "job_agent.handlers.base_handler.resolve",
            return_value="Goran",
        ):
            result = await handler.continue_apply()

        self.assertEqual(browser.opened_urls, [])
        self.assertEqual(browser.filled_values, [("field-1", "Goran")])
        self.assertTrue(result["continued"])
        self.assertFalse(browser.apply_clicked)
