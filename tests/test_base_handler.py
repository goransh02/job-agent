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
    def __init__(self):
        self.page = object()
        self.opened_urls = []
        self.filled_values = []
        self.submit_clicked = False

    def open(self, url):
        self.opened_urls.append(url)

    def fill(self, element, value):
        self.filled_values.append((element, value))
        return True

    def click_submit(self):
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
        store_answer.assert_called_once_with("Custom question", "Manual answer")

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
