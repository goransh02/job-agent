import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from job_agent.browser.playwright_browser import Browser


class FakeElement:
    def __init__(
        self,
        *,
        tag_name="input",
        input_type="text",
        role="",
        has_popup="",
        aria_autocomplete="",
        fill_works=True,
    ):
        self.tag_name = tag_name
        self.attrs = {
            "type": input_type,
            "role": role,
            "aria-haspopup": has_popup,
            "aria-autocomplete": aria_autocomplete,
        }
        self.fill_works = fill_works
        self.fill_calls = []
        self.select_option_calls = []
        self.check_calls = 0
        self.uncheck_calls = 0
        self.click_calls = 0

    async def evaluate(self, script, *args):
        if "tagName" in script:
            return self.tag_name
        return None

    async def get_attribute(self, name):
        return self.attrs.get(name, "")

    async def fill(self, value):
        self.fill_calls.append(value)
        if not self.fill_works:
            raise RuntimeError("fill not supported")

    async def type(self, value):
        self.fill_calls.append(f"type:{value}")

    async def select_option(self, **kwargs):
        self.select_option_calls.append(kwargs)

    async def set_input_files(self, value):
        self.fill_calls.append(f"file:{value}")

    async def is_checked(self):
        return False

    async def check(self):
        self.check_calls += 1

    async def uncheck(self):
        self.uncheck_calls += 1

    async def click(self):
        self.click_calls += 1


class DetachedScope:
    url = "https://jobs.example.com/chat"

    async def query_selector_all(self, selector):
        raise RuntimeError("Frame was detached")


class FakeScope:
    def __init__(self, elements=None, url="https://jobs.example.com/form"):
        self._elements = elements or []
        self.url = url

    async def query_selector_all(self, selector):
        return list(self._elements)


class FakePage:
    def __init__(self):
        self.default_timeout = None
        self.close_calls = 0

    def set_default_timeout(self, value):
        self.default_timeout = value

    async def close(self):
        self.close_calls += 1


class FakeContext:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.new_page_calls = 0
        self.closed = False

    async def new_page(self):
        self.new_page_calls += 1
        page = FakePage()
        self.pages.append(page)
        return page

    async def close(self):
        self.closed = True


class FakeBrowserInstance:
    def __init__(self, contexts=None):
        self.contexts = list(contexts or [])
        self.new_context_calls = 0
        self.closed = False

    async def new_context(self):
        self.new_context_calls += 1
        context = FakeContext()
        self.contexts.append(context)
        return context

    async def close(self):
        self.closed = True


class FakePlaywrightHandle:
    def __init__(self, chromium):
        self.chromium = chromium
        self.stopped = False

    async def stop(self):
        self.stopped = True


class FakePlaywrightStarter:
    def __init__(self, handle):
        self.handle = handle
        self.start_calls = 0

    async def start(self):
        self.start_calls += 1
        return self.handle


class FakeCDPSession:
    def __init__(self, on_create_target=None):
        self.on_create_target = on_create_target
        self.send_calls = []
        self.detached = False

    async def send(self, method, params=None):
        self.send_calls.append((method, params))
        if self.on_create_target is not None and method == "Target.createTarget":
            await self.on_create_target()
        return {"targetId": "target-1"}

    async def detach(self):
        self.detached = True


class BrowserFillTests(unittest.IsolatedAsyncioTestCase):
    async def test_fill_uses_native_select_for_select_elements(self):
        browser = Browser(headless=True)
        browser.page = SimpleNamespace(frames=[], keyboard=SimpleNamespace())
        element = FakeElement(tag_name="select")

        filled = await browser.fill(
            {
                "element": element,
                "tag_name": "select",
                "input_type": "",
                "role": "",
            },
            "Mobile",
        )

        self.assertTrue(filled)
        self.assertGreaterEqual(len(element.select_option_calls), 1)

    async def test_fill_routes_combobox_like_controls_to_combobox_helper(self):
        browser = Browser(headless=True)
        browser.page = SimpleNamespace(frames=[], keyboard=SimpleNamespace())
        element = FakeElement(tag_name="button", role="combobox", fill_works=False)

        with patch.object(browser, "_fill_combobox", AsyncMock(return_value=True)) as combobox_fill:
            filled = await browser.fill(
                {
                    "element": element,
                    "tag_name": "button",
                    "input_type": "",
                    "role": "combobox",
                },
                "LinkedIn",
            )

        self.assertTrue(filled)
        combobox_fill.assert_awaited_once_with(element, "LinkedIn")

    async def test_fill_checks_checkbox_for_truthy_value(self):
        browser = Browser(headless=True)
        browser.page = SimpleNamespace(frames=[], keyboard=SimpleNamespace())
        element = FakeElement(tag_name="input", input_type="checkbox")

        filled = await browser.fill(
            {
                "element": element,
                "tag_name": "input",
                "input_type": "checkbox",
                "role": "",
            },
            "yes",
        )

        self.assertTrue(filled)
        self.assertEqual(element.check_calls, 1)

    async def test_click_submit_uses_scroll_aware_action_search(self):
        browser = Browser(headless=True)

        with patch.object(browser, "_click_best_action", AsyncMock(return_value=True)) as click_best_action:
            clicked = await browser.click_submit()

        self.assertTrue(clicked)
        click_best_action.assert_awaited_once()
        self.assertEqual(click_best_action.await_args.args[0], "submit")

    def test_apply_scoring_ignores_register_and_prefers_real_apply_ctas(self):
        browser = Browser(headless=True)

        self.assertLessEqual(browser._score_apply_action("Register"), 0)
        self.assertLessEqual(browser._score_apply_action("Get Started"), 0)
        self.assertLessEqual(browser._score_apply_action("Apply With LinkedIn"), 0)
        self.assertGreater(browser._score_apply_action("Apply Manually"), 0)

    async def test_click_matching_option_ignores_detached_frames(self):
        browser = Browser(headless=True)
        option = FakeElement(tag_name="div")
        browser.page = SimpleNamespace(
            frames=[DetachedScope(), FakeScope(elements=[option])],
            keyboard=SimpleNamespace(),
        )

        with patch.object(browser, "_is_visible", AsyncMock(return_value=True)), patch.object(
            browser,
            "_get_action_text",
            AsyncMock(return_value="India +91"),
        ):
            clicked = await browser._click_matching_option("India")

        self.assertTrue(clicked)
        self.assertEqual(option.click_calls, 1)

    async def test_upload_resume_uses_hidden_file_input_when_available(self):
        browser = Browser(headless=True)
        file_input = FakeElement(tag_name="input", input_type="file")
        browser.page = SimpleNamespace(
            frames=[FakeScope(elements=[file_input])],
            keyboard=SimpleNamespace(),
        )

        with TemporaryDirectory() as temp_dir:
            resume_path = Path(temp_dir) / "resume.pdf"
            resume_path.write_bytes(b"resume")

            uploaded = await browser.upload_resume(resume_path)

        self.assertTrue(uploaded)
        self.assertEqual(file_input.fill_calls, [f"file:{resume_path}"])

    async def test_start_uses_persistent_context_when_enabled(self):
        browser = Browser(
            headless=False,
            use_persistent_context=True,
            user_data_dir="/tmp/job-agent-profile",
            browser_channel="chrome",
        )
        chromium = SimpleNamespace(
            launch=AsyncMock(),
            launch_persistent_context=AsyncMock(return_value=FakeContext()),
            connect_over_cdp=AsyncMock(),
        )
        playwright_handle = FakePlaywrightHandle(chromium)
        starter = FakePlaywrightStarter(playwright_handle)

        with patch("job_agent.browser.playwright_browser._load_async_playwright", return_value=lambda: starter):
            await browser.start()

        chromium.launch_persistent_context.assert_awaited_once()
        chromium.launch.assert_not_awaited()
        chromium.connect_over_cdp.assert_not_awaited()
        self.assertIsNotNone(browser.page)

    async def test_start_attaches_to_existing_browser_over_cdp(self):
        browser = Browser(
            headless=False,
            cdp_url="http://127.0.0.1:9222",
        )
        shared_context = FakeContext()
        cdp_session = FakeCDPSession(
            on_create_target=shared_context.new_page,
        )
        attached_browser = FakeBrowserInstance(contexts=[shared_context])
        attached_browser.new_browser_cdp_session = AsyncMock(return_value=cdp_session)
        chromium = SimpleNamespace(
            launch=AsyncMock(),
            launch_persistent_context=AsyncMock(),
            connect_over_cdp=AsyncMock(return_value=attached_browser),
        )
        playwright_handle = FakePlaywrightHandle(chromium)
        starter = FakePlaywrightStarter(playwright_handle)

        with patch("job_agent.browser.playwright_browser._load_async_playwright", return_value=lambda: starter):
            await browser.start()

        chromium.connect_over_cdp.assert_awaited_once_with("http://127.0.0.1:9222")
        chromium.launch.assert_not_awaited()
        chromium.launch_persistent_context.assert_not_awaited()
        attached_browser.new_browser_cdp_session.assert_awaited_once()
        self.assertEqual(cdp_session.send_calls[0][0], "Target.createTarget")
        self.assertTrue(cdp_session.send_calls[0][1]["newWindow"])
        self.assertTrue(cdp_session.detached)
        self.assertEqual(shared_context.new_page_calls, 1)
        self.assertIsNotNone(browser.page)

    async def test_close_does_not_close_attached_browser_instance(self):
        browser = Browser(headless=False, cdp_url="http://127.0.0.1:9222")
        browser._connected_over_cdp = True
        browser.page = FakePage()
        browser.context = FakeContext()
        browser.browser = FakeBrowserInstance()
        browser.playwright = FakePlaywrightHandle(SimpleNamespace())

        await browser.close()

        self.assertEqual(browser.page, None)
        self.assertIsNone(browser.context)
        self.assertIsNone(browser.browser)
        self.assertTrue(browser.playwright is None or browser.playwright.stopped)
