from __future__ import annotations

from pathlib import Path

from job_agent.config import (
    BROWSER_HEADLESS,
    BROWSER_SLOW_MO_MS,
    BROWSER_TIMEOUT_MS,
)


class Browser:
    def __init__(self, headless: bool | None = None) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run `pip install -r job_agent/requirements.txt` "
                "and `playwright install chromium`."
            ) from exc

        self._playwright_manager = sync_playwright()
        self.playwright = self._playwright_manager.start()
        self.browser = self.playwright.chromium.launch(
            headless=BROWSER_HEADLESS if headless is None else headless,
            slow_mo=BROWSER_SLOW_MO_MS,
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.set_default_timeout(BROWSER_TIMEOUT_MS)

    def open(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")

    def get_inputs(self):
        return self.page.query_selector_all("input, textarea, select")

    def fill(self, element, value) -> bool:
        if value in (None, ""):
            return False

        input_type = (element.get_attribute("type") or "").lower()

        if input_type == "file":
            path = Path(str(value))
            if not path.exists():
                return False
            element.set_input_files(str(path))
            return True

        try:
            element.fill(str(value))
            return True
        except Exception:
            try:
                element.select_option(label=str(value))
                return True
            except Exception:
                return False

    def click_submit(self) -> bool:
        for selector in ('button', 'input[type="submit"]'):
            elements = self.page.query_selector_all(selector)

            for element in elements:
                try:
                    text = (element.inner_text() or "").lower()
                except Exception:
                    text = (element.get_attribute("value") or "").lower()

                if "apply" not in text and "submit" not in text and "send" not in text:
                    continue

                try:
                    element.click()
                    return True
                except Exception:
                    continue

        return False

    def close(self) -> None:
        self.context.close()
        self.browser.close()
        self.playwright.stop()
