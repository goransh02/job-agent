from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from job_agent.agent.form_parser import FORM_FIELD_SELECTOR, parse_fields
from job_agent.agent.page_analyzer import detect_errors
from job_agent.config import (
    BROWSER_CDP_URL,
    BROWSER_CDP_NEW_WINDOW,
    BROWSER_HEADLESS,
    BROWSER_CHANNEL,
    BROWSER_FORM_WAIT_TIMEOUT_MS,
    BROWSER_SLOW_MO_MS,
    BROWSER_STEP_WAIT_TIMEOUT_MS,
    BROWSER_TIMEOUT_MS,
    BROWSER_USE_PERSISTENT_CONTEXT,
    BROWSER_USER_DATA_DIR,
)
from job_agent.logging_utils import trace

logger = logging.getLogger(__name__)

ACTIONABLE_INPUT_TYPES = {
    "",
    "date",
    "datetime-local",
    "email",
    "file",
    "number",
    "search",
    "tel",
    "text",
    "url",
}

SKIP_INPUT_TYPES = {
    "button",
    "checkbox",
    "hidden",
    "image",
    "password",
    "radio",
    "reset",
    "submit",
}

PREFERRED_APPLY_TEXT_HINTS = (
    "apply manually",
    "manual apply",
    "continue application",
    "start your application",
    "start application",
)

PREFERRED_NEXT_TEXT_HINTS = (
    "next",
    "continue",
    "save and continue",
    "continue to review",
    "review",
)

PREFERRED_REGISTER_TEXT_HINTS = (
    "create account",
    "register",
    "sign up",
)

PREFERRED_RESUME_TEXT_HINTS = (
    "upload resume",
    "upload cv",
    "upload resume/cv",
    "attach resume",
    "attach cv",
    "attach",
    "browse",
)

PREFERRED_COVER_LETTER_TEXT_HINTS = (
    "upload cover letter",
    "attach cover letter",
    "upload letter",
    "attach letter",
    "attach",
    "browse",
)

APPLY_TEXT_HINTS = (
    "apply",
    "easy apply",
    "apply now",
    "apply for this job",
    "start application",
    "start your application",
    "continue application",
)

NEXT_TEXT_HINTS = (
    "next",
    "continue",
    "save and continue",
    "continue to review",
    "review",
)

SKIP_APPLY_TEXT_HINTS = (
    "autofill with resume",
    "resume",
    "last application",
    "register",
    "registration",
    "sign up",
    "submit",
    "create alert",
    "job alert",
    "get started",
    "linkedin",
    "dropbox",
    "google drive",
    "onedrive",
    "sign in",
    "log in",
)

SKIP_NEXT_TEXT_HINTS = (
    "apply manually",
    "autofill with resume",
    "resume",
    "last application",
    "submit",
    "send",
    "sign in",
    "log in",
)

ACTION_SELECTORS = (
    "button",
    "a",
    '[role="button"]',
    'input[type="button"]',
    'input[type="submit"]',
)

OPTION_SELECTORS = (
    '[role="option"]',
    '[data-automation-id="promptOption"]',
    '[data-automation-id="menuItem"]',
    '[data-automation-id*="option"]',
    '[data-automation-id*="Option"]',
    "li[role='option']",
)

FILE_INPUT_SELECTOR = "input[type='file']"

SCROLL_STEP_RATIO = 0.72
SCROLL_SETTLE_SECONDS = 0.3


def _load_async_playwright():
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run `pip install -r job_agent/requirements.txt` "
            "and `python3 -m playwright install chromium`."
        ) from exc

    return async_playwright


class Browser:
    def __init__(
        self,
        headless: bool | None = None,
        *,
        use_persistent_context: bool | None = None,
        user_data_dir: str | Path | None = None,
        browser_channel: str | None = None,
        cdp_url: str | None = None,
        cdp_new_window: bool | None = None,
    ) -> None:
        self.headless = BROWSER_HEADLESS if headless is None else headless
        self.use_persistent_context = (
            BROWSER_USE_PERSISTENT_CONTEXT
            if use_persistent_context is None
            else use_persistent_context
        )
        self.user_data_dir = Path(
            BROWSER_USER_DATA_DIR if user_data_dir is None else user_data_dir
        ).expanduser()
        self.browser_channel = BROWSER_CHANNEL if browser_channel is None else browser_channel
        self.cdp_url = BROWSER_CDP_URL if cdp_url is None else cdp_url
        self.cdp_new_window = BROWSER_CDP_NEW_WINDOW if cdp_new_window is None else cdp_new_window
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._connected_over_cdp = False
        self._persistent_context = False

    @property
    def mode(self) -> str:
        if self._connected_over_cdp:
            if self.cdp_new_window:
                return "attached-cdp-new-window"
            return "attached-cdp-tab"
        if self.use_persistent_context:
            return "persistent-profile"
        return "fresh-playwright"

    def _launch_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "headless": self.headless,
            "slow_mo": BROWSER_SLOW_MO_MS,
        }
        if self.browser_channel:
            kwargs["channel"] = self.browser_channel
        return kwargs

    async def _initialize_page(self) -> None:
        if self.context is None:
            raise RuntimeError("Browser context is not initialized")

        existing_pages = getattr(self.context, "pages", []) or []
        if existing_pages:
            self.page = existing_pages[-1]
        else:
            self.page = await self.context.new_page()

        self.page.set_default_timeout(BROWSER_TIMEOUT_MS)

    async def _attach_to_cdp_browser(self) -> None:
        trace(logger, "Connecting to existing browser over CDP: %s", self.cdp_url)
        self.browser = await self.playwright.chromium.connect_over_cdp(self.cdp_url)
        self._connected_over_cdp = True

        existing_contexts = list(getattr(self.browser, "contexts", []) or [])
        if existing_contexts:
            self.context = existing_contexts[0]
        else:
            self.context = await self.browser.new_context()

        if self.cdp_new_window:
            self.page = await self._open_cdp_window()
        else:
            self.page = await self.context.new_page()
        self.page.set_default_timeout(BROWSER_TIMEOUT_MS)

    async def _open_cdp_window(self):
        existing_pages = list(getattr(self.context, "pages", []) or [])
        existing_page_ids = {id(page) for page in existing_pages}
        cdp_session = await self.browser.new_browser_cdp_session()

        try:
            trace(logger, "Requesting a new Chrome window over CDP")
            await cdp_session.send(
                "Target.createTarget",
                {
                    "url": "about:blank",
                    "newWindow": True,
                },
            )

            deadline = asyncio.get_running_loop().time() + 5
            while asyncio.get_running_loop().time() < deadline:
                for candidate in getattr(self.context, "pages", []) or []:
                    if id(candidate) not in existing_page_ids:
                        trace(logger, "Attached to new Chrome window created over CDP")
                        return candidate
                await asyncio.sleep(0.2)
        except Exception:
            logger.exception("Failed to create a new Chrome window over CDP; falling back to a new tab")
        finally:
            try:
                await cdp_session.detach()
            except Exception:
                pass

        return await self.context.new_page()

    async def _launch_persistent_context(self) -> None:
        launch_kwargs = self._launch_kwargs()
        trace(
            logger,
            "Launching Playwright persistent context (headless=%s, channel=%s, user_data_dir=%s)",
            self.headless,
            self.browser_channel or "<default>",
            self.user_data_dir,
        )
        self.context = await self.playwright.chromium.launch_persistent_context(
            str(self.user_data_dir),
            **launch_kwargs,
        )
        self._persistent_context = True
        await self._initialize_page()

    async def start(self) -> None:
        if self.page is not None:
            trace(logger, "Browser already started")
            return

        async_playwright = _load_async_playwright()

        trace(
            logger,
            "Starting Playwright browser (headless=%s, persistent=%s, cdp=%s, channel=%s)",
            self.headless,
            self.use_persistent_context,
            bool(self.cdp_url),
            self.browser_channel or "<default>",
        )
        self.playwright = await async_playwright().start()
        if self.cdp_url:
            await self._attach_to_cdp_browser()
        elif self.use_persistent_context:
            await self._launch_persistent_context()
        else:
            self.browser = await self.playwright.chromium.launch(**self._launch_kwargs())
            self.context = await self.browser.new_context()
            await self._initialize_page()
        trace(logger, "Playwright browser started successfully")

    async def open(self, url: str) -> None:
        await self.start()
        trace(logger, "Navigating browser to %s", url)
        await self.page.goto(url, wait_until="domcontentloaded")
        trace(logger, "Navigation completed for %s", url)

    async def get_inputs(self):
        await self.start()
        return await self.page.query_selector_all("input, textarea, select")

    async def _safe_inner_text(self, element) -> str:
        try:
            return ((await element.inner_text()) or "").strip()
        except Exception:
            return ""

    async def _is_visible(self, element) -> bool:
        try:
            return await element.is_visible()
        except Exception:
            return False

    def _is_recoverable_dom_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "frame was detached" in message
            or "element is not attached" in message
            or "execution context was destroyed" in message
            or "target page, context or browser has been closed" in message
            or "browser has been closed" in message
        )

    async def _safe_query_selector_all(self, scope, selector: str):
        try:
            return await scope.query_selector_all(selector)
        except Exception as exc:
            if self._is_recoverable_dom_error(exc):
                trace(
                    logger,
                    "Skipping detached scope while querying selector '%s' in '%s'",
                    selector,
                    getattr(scope, "url", "") or "<unknown>",
                )
                return []
            raise

    async def _get_action_text(self, element) -> str:
        parts = [
            await self._safe_inner_text(element),
            (await element.get_attribute("value")) or "",
            (await element.get_attribute("aria-label")) or "",
            (await element.get_attribute("title")) or "",
        ]
        return " ".join(part.strip() for part in parts if part and part.strip()).lower()

    async def has_form_fields(self) -> bool:
        await self.start()

        for frame in self.page.frames:
            for element in await self._safe_query_selector_all(frame, FORM_FIELD_SELECTOR):
                tag_name = (await element.evaluate("(node) => node.tagName.toLowerCase()")) or ""
                if tag_name == "input":
                    input_type = ((await element.get_attribute("type")) or "").lower()
                    if input_type in SKIP_INPUT_TYPES:
                        continue
                    if input_type not in ACTIONABLE_INPUT_TYPES and input_type not in SKIP_INPUT_TYPES:
                        trace(
                            logger,
                            "Treating uncommon input type '%s' as actionable",
                            input_type,
                        )

                if await self._is_visible(element):
                    return True

        return False

    def _normalize_text(self, value: str) -> str:
        return " ".join((value or "").strip().lower().split())

    def _is_truthy_value(self, value) -> bool:
        normalized = self._normalize_text(str(value))
        return normalized in {"1", "true", "yes", "y", "checked", "on", "mobile"}

    def _extract_field_parts(self, field_or_element):
        if isinstance(field_or_element, dict):
            return field_or_element["element"], field_or_element

        return field_or_element, {}

    def _score_apply_action(self, action_text: str) -> int:
        normalized = self._normalize_text(action_text)
        score = 0

        if any(hint in normalized for hint in SKIP_APPLY_TEXT_HINTS):
            return -500

        has_apply_context = "apply" in normalized or "application" in normalized
        if not has_apply_context:
            return -100

        if any(hint in normalized for hint in PREFERRED_APPLY_TEXT_HINTS):
            score += 120

        if "apply manually" in normalized:
            score += 180
        elif "apply for this job" in normalized:
            score += 150
        elif "apply now" in normalized:
            score += 130
        elif "apply" in normalized:
            score += 100

        if "application" in normalized and "start" in normalized:
            score += 70

        if "application" in normalized and "continue" in normalized:
            score += 60

        if "submit application" in normalized:
            score += 40

        return score

    def _score_next_action(self, action_text: str) -> int:
        score = 0

        if any(hint in action_text for hint in PREFERRED_NEXT_TEXT_HINTS):
            score += 100

        if "next" in action_text:
            score += 120

        if "save and continue" in action_text:
            score += 90
        elif "continue" in action_text:
            score += 70

        if "review" in action_text:
            score += 50

        if any(hint in action_text for hint in SKIP_NEXT_TEXT_HINTS):
            score -= 300

        return score

    def _score_submit_action(self, action_text: str) -> int:
        score = 0

        if "submit" in action_text:
            score += 140

        if "review" in action_text:
            score += 80

        if "send" in action_text:
            score += 70

        if "continue" in action_text and "review" in action_text:
            score += 60

        if any(
            hint in action_text
            for hint in ("apply manually", "autofill with resume", "last application", "sign in", "log in")
        ):
            score -= 300

        return score

    def _score_resume_action(self, action_text: str) -> int:
        return self._score_document_action(action_text, "resume")

    def _score_cover_letter_action(self, action_text: str) -> int:
        return self._score_document_action(action_text, "cover_letter")

    def _score_register_action(self, action_text: str) -> int:
        normalized = self._normalize_text(action_text)
        score = 0

        if "login" in normalized or "sign in" in normalized:
            score -= 200

        if any(hint in normalized for hint in PREFERRED_REGISTER_TEXT_HINTS):
            score += 180

        if "create account" in normalized:
            score += 220
        elif "register" in normalized:
            score += 150
        elif "sign up" in normalized:
            score += 140

        return score

    def _score_document_action(self, action_text: str, document_type: str, context_text: str = "") -> int:
        normalized = self._normalize_text(action_text)
        normalized_context = self._normalize_text(context_text)
        score = 0

        if any(
            hint in normalized
            for hint in ("linkedin", "dropbox", "google drive", "onedrive", "cloud")
        ):
            return -400

        if document_type == "resume":
            if any(hint in normalized for hint in PREFERRED_RESUME_TEXT_HINTS):
                score += 140
            if "resume" in normalized or "cv" in normalized:
                score += 120
            if any(hint in normalized_context for hint in ("resume", "resume/cv", "cv")):
                score += 150
        else:
            if any(hint in normalized for hint in PREFERRED_COVER_LETTER_TEXT_HINTS):
                score += 140
            if "cover letter" in normalized:
                score += 140
            if any(hint in normalized_context for hint in ("cover letter", "letter")):
                score += 170

        if "upload" in normalized:
            score += 100

        if "attach" in normalized:
            score += 90

        if "enter manually" in normalized:
            score -= 120

        return score

    async def _get_action_context_text(self, element) -> str:
        try:
            text = await element.evaluate(
                """(node) => {
                    const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
                    let current = node.parentElement;
                    let best = "";

                    for (let depth = 0; current && depth < 6; depth += 1) {
                        const text = clean(current.innerText || current.textContent || "");
                        if (text.length > best.length) {
                            best = text;
                        }
                        current = current.parentElement;
                    }

                    return best;
                }"""
            )
        except Exception:
            return ""

        return self._normalize_text(text or "")

    async def _scroll_main_page(self, direction: str = "down") -> bool:
        await self.start()

        if direction == "top":
            before = await self.page.evaluate("() => window.scrollY")
            await self.page.evaluate("() => window.scrollTo({ top: 0, behavior: 'auto' })")
            await asyncio.sleep(SCROLL_SETTLE_SECONDS)
            after = await self.page.evaluate("() => window.scrollY")
            moved = before != after
            if moved:
                trace(logger, "Scrolled page to top")
            return moved

        before = await self.page.evaluate("() => window.scrollY")
        after = await self.page.evaluate(
            """(ratio) => {
                const delta = Math.max(window.innerHeight * ratio, 260);
                window.scrollBy({ top: delta, behavior: 'auto' });
                return window.scrollY;
            }""",
            SCROLL_STEP_RATIO,
        )
        await asyncio.sleep(SCROLL_SETTLE_SECONDS)
        moved = after != before
        if moved:
            trace(logger, "Scrolled page downward from %s to %s", before, after)
        return moved

    async def scroll_for_form_fields(self, max_scrolls: int = 4) -> bool:
        await self.start()

        if await self.has_form_fields():
            return True

        for attempt in range(1, max_scrolls + 1):
            moved = await self._scroll_main_page()
            if not moved:
                trace(logger, "No additional page scroll movement available while searching for fields")
                break

            if await self.has_form_fields():
                trace(logger, "Detected form fields after scroll attempt %s", attempt)
                return True

        return False

    async def _click_best_action(
        self,
        description: str,
        score_action,
        timeout_ms: int | None = None,
    ) -> bool:
        await self.start()
        trace(logger, "Looking for %s button or link", description)

        timeout = BROWSER_FORM_WAIT_TIMEOUT_MS if timeout_ms is None else timeout_ms
        deadline = asyncio.get_running_loop().time() + (timeout / 1000)
        logged_candidates = set()
        reset_to_top = False

        while asyncio.get_running_loop().time() < deadline:
            ranked_candidates = []

            for frame in self.page.frames:
                for selector in ACTION_SELECTORS:
                    elements = await self._safe_query_selector_all(frame, selector)

                    for element in elements:
                        if not await self._is_visible(element):
                            continue

                        action_text = await self._get_action_text(element)
                        if not action_text:
                            continue

                        candidate_key = (frame.url or "<main>", selector, action_text)
                        if candidate_key not in logged_candidates:
                            logged_candidates.add(candidate_key)
                            trace(
                                logger,
                                "Saw %s candidate in frame '%s': %s",
                                description,
                                frame.url or "<main>",
                                action_text,
                            )

                        score = score_action(action_text)
                        if score <= 0:
                            continue

                        ranked_candidates.append(
                            (score, selector, frame, element, action_text),
                        )

            ranked_candidates.sort(key=lambda candidate: candidate[0], reverse=True)

            for score, selector, frame, element, action_text in ranked_candidates:
                try:
                    await element.scroll_into_view_if_needed()
                except Exception:
                    pass

                try:
                    await element.click()
                    trace(
                        logger,
                        "Clicked %s element using selector %s in frame '%s' with text '%s' (score=%s)",
                        description,
                        selector,
                        frame.url or "<main>",
                        action_text,
                        score,
                    )
                    return True
                except Exception:
                    try:
                        await element.evaluate("(node) => node.click()")
                        trace(
                            logger,
                            "Clicked %s element via JS using selector %s in frame '%s' with text '%s' (score=%s)",
                            description,
                            selector,
                            frame.url or "<main>",
                            action_text,
                            score,
                        )
                        return True
                    except Exception:
                        logger.exception(
                            "Failed to click %s element using selector %s with text '%s'",
                            description,
                            selector,
                            action_text,
                        )

            moved = await self._scroll_main_page()
            if moved:
                continue

            if not reset_to_top:
                reset_to_top = True
                await self._scroll_main_page(direction="top")
                continue

            await asyncio.sleep(0.5)

        trace(logger, "No %s button or link found", description)
        return False

    async def _click_matching_option(self, value: str) -> bool:
        target = self._normalize_text(str(value))
        if not target:
            return False

        best_candidate = None

        for frame in self.page.frames:
            for selector in OPTION_SELECTORS:
                options = await self._safe_query_selector_all(frame, selector)

                for option in options:
                    if not await self._is_visible(option):
                        continue

                    option_text = self._normalize_text(await self._get_action_text(option))
                    if not option_text:
                        continue

                    score = 0
                    if option_text == target:
                        score = 300
                    elif target in option_text:
                        score = 200
                    elif option_text in target:
                        score = 100

                    if score <= 0:
                        continue

                    if best_candidate is None or score > best_candidate[0]:
                        best_candidate = (score, frame, option, option_text)

        if best_candidate is None:
            return False

        _, frame, option, option_text = best_candidate

        try:
            await option.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            await option.click()
            trace(
                logger,
                "Clicked option in frame '%s' with text '%s'",
                frame.url or "<main>",
                option_text,
            )
            return True
        except Exception:
            try:
                await option.evaluate("(node) => node.click()")
                trace(
                    logger,
                    "Clicked option via JS in frame '%s' with text '%s'",
                    frame.url or "<main>",
                    option_text,
                )
                return True
            except Exception:
                logger.exception("Failed to click option with text '%s'", option_text)
                return False

    async def _clear_text_input(self, element) -> None:
        for shortcut in ("Meta+A", "Control+A"):
            try:
                await element.press(shortcut)
                break
            except Exception:
                continue

        for key in ("Backspace", "Delete"):
            try:
                await element.press(key)
                return
            except Exception:
                continue

    async def _set_text_value(self, element, value: str) -> bool:
        try:
            await element.fill(str(value))
            return True
        except Exception:
            pass

        try:
            await element.type(str(value))
            return True
        except Exception:
            pass

        try:
            await element.evaluate(
                """(node, nextValue) => {
                    node.focus();
                    node.value = nextValue;
                    node.dispatchEvent(new Event("input", { bubbles: true }));
                    node.dispatchEvent(new Event("change", { bubbles: true }));
                }""",
                str(value),
            )
            return True
        except Exception:
            return False

    async def _find_visible_editor(self):
        search_selectors = (
            "input[role='combobox']",
            "input[aria-autocomplete='list']",
            "input[aria-autocomplete='both']",
            "input[type='search']",
            "input:not([type='hidden']):not([type='button']):not([type='submit'])",
            "textarea",
        )

        for frame in self.page.frames:
            for selector in search_selectors:
                for candidate in await self._safe_query_selector_all(frame, selector):
                    if await self._is_visible(candidate):
                        return candidate

        return None

    async def _fill_combobox(self, element, value: str) -> bool:
        trace(logger, "Attempting combobox fill with value '%s'", value)

        try:
            await element.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            await element.click()
        except Exception:
            logger.exception("Failed to focus combobox element")

        if await self._click_matching_option(value):
            return True

        editor = await self._find_visible_editor()
        if editor is not None and editor is not element:
            try:
                await editor.click()
            except Exception:
                pass

            try:
                await self._clear_text_input(editor)
            except Exception:
                pass

            if await self._set_text_value(editor, str(value)):
                await asyncio.sleep(0.3)
                if await self._click_matching_option(value):
                    return True

                for key in ("ArrowDown", "Enter"):
                    try:
                        await self.page.keyboard.press(key)
                    except Exception:
                        continue
                    await asyncio.sleep(0.2)
                    if await self._click_matching_option(value):
                        return True

        try:
            await self._clear_text_input(element)
        except Exception:
            pass

        typed = await self._set_text_value(element, str(value))
        if not typed:
            try:
                await self.page.keyboard.type(str(value))
                typed = True
            except Exception:
                typed = False

        await asyncio.sleep(0.3)
        if await self._click_matching_option(value):
            return True

        if typed:
            for key in ("Enter", "ArrowDown", "Enter"):
                try:
                    await self.page.keyboard.press(key)
                except Exception:
                    continue
                await asyncio.sleep(0.2)
                if await self._click_matching_option(value):
                    return True

            return True

        return False

    async def _set_checked_state(self, element, checked: bool) -> bool:
        try:
            current = await element.is_checked()
        except Exception:
            current = None

        if current is not None and current == checked:
            return True

        try:
            if checked:
                await element.check()
            else:
                await element.uncheck()
            return True
        except Exception:
            pass

        try:
            await element.click()
            return True
        except Exception:
            return False

    async def _select_native_option(self, element, value: str) -> bool:
        try:
            await element.select_option(label=str(value))
            return True
        except Exception:
            pass

        try:
            await element.select_option(value=str(value))
            return True
        except Exception:
            pass

        try:
            options = await element.query_selector_all("option")
        except Exception:
            return False

        target = self._normalize_text(value)
        matched_option_value = None

        for option in options:
            option_text = self._normalize_text(await self._safe_inner_text(option))
            option_value = self._normalize_text((await option.get_attribute("value")) or "")
            if option_text == target or option_value == target:
                matched_option_value = (await option.get_attribute("value")) or await self._safe_inner_text(option)
                break

            if target and (target in option_text or option_text in target):
                matched_option_value = (await option.get_attribute("value")) or await self._safe_inner_text(option)

        if matched_option_value is None:
            return False

        try:
            await element.select_option(value=matched_option_value)
            return True
        except Exception:
            try:
                await element.select_option(label=matched_option_value)
                return True
            except Exception:
                return False

    async def _set_first_available_file_input(self, path: Path) -> bool:
        for frame in self.page.frames:
            for candidate in await self._safe_query_selector_all(frame, FILE_INPUT_SELECTOR):
                try:
                    await candidate.set_input_files(str(path))
                    trace(
                        logger,
                        "Attached resume using file input in frame '%s'",
                        frame.url or "<main>",
                    )
                    return True
                except Exception as exc:
                    if self._is_recoverable_dom_error(exc):
                        continue
                    logger.exception("Failed to set files on candidate resume input")

        return False

    async def has_document_upload_controls(self, document_type: str = "resume") -> bool:
        await self.start()

        for frame in self.page.frames:
            file_inputs = await self._safe_query_selector_all(frame, FILE_INPUT_SELECTOR)
            if file_inputs and document_type == "resume":
                return True

            for selector in ACTION_SELECTORS:
                for element in await self._safe_query_selector_all(frame, selector):
                    if not await self._is_visible(element):
                        continue

                    action_text = await self._get_action_text(element)
                    if not action_text:
                        continue

                    context_text = await self._get_action_context_text(element)
                    if self._score_document_action(action_text, document_type, context_text) > 0:
                        return True

        return False

    async def has_resume_upload_controls(self) -> bool:
        return await self.has_document_upload_controls("resume")

    async def has_auth_gate(self) -> bool:
        await self.start()

        for frame in self.page.frames:
            for input_type in ("password",):
                password_inputs = await self._safe_query_selector_all(frame, f"input[type='{input_type}']")
                for element in password_inputs:
                    if await self._is_visible(element):
                        return True

            for selector in ACTION_SELECTORS:
                for element in await self._safe_query_selector_all(frame, selector):
                    if not await self._is_visible(element):
                        continue
                    action_text = await self._get_action_text(element)
                    if self._score_register_action(action_text) > 0:
                        return True

        return False

    async def upload_document(self, path_like, document_type: str = "resume") -> bool:
        await self.start()

        path = Path(str(path_like))
        if not path.exists():
            logger.warning("%s upload path does not exist: %s", document_type, path)
            return False

        ranked_candidates = []
        for frame in self.page.frames:
            for selector in ACTION_SELECTORS:
                elements = await self._safe_query_selector_all(frame, selector)
                for element in elements:
                    if not await self._is_visible(element):
                        continue

                    action_text = await self._get_action_text(element)
                    if not action_text:
                        continue

                    context_text = await self._get_action_context_text(element)
                    score = self._score_document_action(action_text, document_type, context_text)
                    if score <= 0:
                        continue

                    ranked_candidates.append((score, frame, element, selector, action_text))

        ranked_candidates.sort(key=lambda candidate: candidate[0], reverse=True)

        for score, frame, element, selector, action_text in ranked_candidates:
            try:
                await element.scroll_into_view_if_needed()
            except Exception:
                pass

            chooser = None
            try:
                async with self.page.expect_file_chooser(timeout=4000) as chooser_info:
                    await element.click()
                chooser = await chooser_info.value
            except Exception:
                chooser = None

            if chooser is not None:
                try:
                    await chooser.set_files(str(path))
                    trace(
                        logger,
                        "Uploaded %s via file chooser using selector %s in frame '%s' with text '%s' (score=%s)",
                        document_type,
                        selector,
                        frame.url or "<main>",
                        action_text,
                        score,
                    )
                    await asyncio.sleep(0.8)
                    return True
                except Exception:
                    logger.exception("Failed to upload resume through file chooser")

            try:
                await element.click()
            except Exception:
                try:
                    await element.evaluate("(node) => node.click()")
                except Exception:
                    logger.exception("Failed to click resume upload control with text '%s'", action_text)
                    continue

            deadline = asyncio.get_running_loop().time() + 4
            while asyncio.get_running_loop().time() < deadline:
                if await self._set_first_available_file_input(path):
                    trace(
                        logger,
                        "Uploaded %s after clicking selector %s in frame '%s' with text '%s' (score=%s)",
                        document_type,
                        selector,
                        frame.url or "<main>",
                        action_text,
                        score,
                    )
                    await asyncio.sleep(0.8)
                    return True
                await asyncio.sleep(0.35)

        if document_type == "resume" and await self._set_first_available_file_input(path):
            await asyncio.sleep(0.8)
            return True

        trace(logger, "No usable %s upload control found", document_type)
        return False

    async def upload_resume(self, path_like) -> bool:
        return await self.upload_document(path_like, "resume")

    async def upload_cover_letter(self, path_like) -> bool:
        return await self.upload_document(path_like, "cover_letter")

    async def click_apply(self) -> bool:
        return await self._click_best_action("apply", self._score_apply_action)

    async def click_create_account(self) -> bool:
        return await self._click_best_action("create-account", self._score_register_action, timeout_ms=4000)

    async def click_next(self) -> bool:
        return await self._click_best_action("next", self._score_next_action, timeout_ms=3000)

    async def wait_for_form_ready(self, timeout_ms: int | None = None) -> bool:
        await self.start()
        timeout = BROWSER_FORM_WAIT_TIMEOUT_MS if timeout_ms is None else timeout_ms
        logger.info("Waiting up to %sms for application form fields or resume controls", timeout)

        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            logger.info("DOM content load wait timed out or was unnecessary")

        deadline = asyncio.get_running_loop().time() + (timeout / 1000)
        while asyncio.get_running_loop().time() < deadline:
            if await self.has_form_fields():
                logger.info("Detected form fields after apply click")
                return True
            if await self.has_document_upload_controls("resume") or await self.has_document_upload_controls("cover_letter"):
                logger.info("Detected resume upload controls while waiting for the next step")
                return True
            await asyncio.sleep(0.5)

        logger.warning("Timed out waiting for form fields or resume controls")
        return False

    async def open_job(self, url: str) -> bool:
        await self.open(url)
        return True

    async def snapshot_form(self) -> list[dict[str, object]]:
        await self.start()
        fields = await parse_fields(self.page)
        snapshot = []
        for index, field in enumerate(fields):
            serialized = dict(field)
            serialized.setdefault("field_id", f"field-{index}")
            serialized["options"] = await self._extract_options(field.get("element"))
            serialized["required"] = await self._is_required(field.get("element"))
            snapshot.append(serialized)
        return snapshot

    async def read_page(self) -> dict[str, object]:
        fields = await self.snapshot_form()
        errors = await detect_errors(self.page)
        return {
            "url": getattr(self.page, "url", "") or "",
            "field_count": len(fields),
            "fields": [
                {
                    "field_id": str(field.get("field_id") or ""),
                    "label": str(field.get("label") or ""),
                    "tag_name": str(field.get("tag_name") or ""),
                    "input_type": str(field.get("input_type") or ""),
                    "role": str(field.get("role") or ""),
                    "required": bool(field.get("required")),
                    "options": list(field.get("options") or []),
                }
                for field in fields
            ],
            "errors": errors,
        }

    async def _extract_options(self, element) -> list[str]:
        if element is None:
            return []
        try:
            options = await element.evaluate(
                """(node) => {
                    if (node.tagName && node.tagName.toLowerCase() === "select") {
                        return Array.from(node.options || [])
                          .map((option) => (option.label || option.textContent || "").trim())
                          .filter(Boolean);
                    }
                    return [];
                }"""
            )
        except Exception:
            return []

        if not isinstance(options, list):
            return []
        return [str(option).strip() for option in options if str(option).strip()]

    async def _is_required(self, element) -> bool:
        if element is None:
            return False
        try:
            required = await element.evaluate(
                """(node) => {
                    if (!node) return false;
                    return Boolean(node.required || node.getAttribute("aria-required") === "true");
                }"""
            )
        except Exception:
            return False
        return bool(required)

    async def fill_text(self, field_or_element, value) -> bool:
        return await self.fill(field_or_element, value)

    async def select_option(self, field_or_element, value) -> bool:
        return await self.fill(field_or_element, value)

    async def fill(self, field_or_element, value) -> bool:
        if value in (None, ""):
            logger.info("Skipping empty value during fill")
            return False

        element, metadata = self._extract_field_parts(field_or_element)
        try:
            tag_name = ((await element.evaluate("(node) => node.tagName.toLowerCase()")) or "").lower()
            input_type = (metadata.get("input_type") or (await element.get_attribute("type")) or "").lower()
            role = (metadata.get("role") or (await element.get_attribute("role")) or "").lower()
            has_popup = ((await element.get_attribute("aria-haspopup")) or "").lower()
            aria_autocomplete = ((await element.get_attribute("aria-autocomplete")) or "").lower()

            if input_type == "file":
                path = Path(str(value))
                if not path.exists():
                    logger.warning("File input path does not exist: %s", path)
                    return False
                await element.set_input_files(str(path))
                return True

            if input_type in {"checkbox", "radio"} or role in {"checkbox", "radio"}:
                return await self._set_checked_state(element, self._is_truthy_value(value))

            if tag_name == "select":
                if await self._select_native_option(element, str(value)):
                    return True

            is_combobox_like = (
                role == "combobox"
                or has_popup == "listbox"
                or aria_autocomplete in {"list", "both"}
                or tag_name in {"button", "div"}
            )
            if is_combobox_like:
                if await self._fill_combobox(element, str(value)):
                    return True

            if await self._set_text_value(element, str(value)):
                return True

            try:
                await element.select_option(label=str(value))
                return True
            except Exception:
                if await self._fill_combobox(element, str(value)):
                    return True
                logger.exception("Failed to fill/select value for element")
                return False
        except Exception as exc:
            if self._is_recoverable_dom_error(exc):
                logger.warning(
                    "Skipping stale field during fill for '%s': %s",
                    metadata.get("label") or metadata.get("scope_url") or "<unknown>",
                    exc,
                )
                return False
            raise

    async def click_submit(self) -> bool:
        return await self._click_best_action("submit", self._score_submit_action, timeout_ms=4000)

    async def close(self) -> None:
        if self._connected_over_cdp:
            if self.page is not None:
                try:
                    logger.info("Closing attached browser page")
                    await self.page.close()
                except Exception:
                    logger.exception("Failed to close attached browser page")
            self.page = None
            self.context = None
            self.browser = None
            self._connected_over_cdp = False
            self._persistent_context = False

            if self.playwright is not None:
                logger.info("Stopping Playwright")
                await self.playwright.stop()
                self.playwright = None
            return

        if self.context is not None:
            logger.info("Closing browser context")
            await self.context.close()
            self.context = None

        if self.browser is not None:
            logger.info("Closing browser instance")
            await self.browser.close()
            self.browser = None

        if self.playwright is not None:
            logger.info("Stopping Playwright")
            await self.playwright.stop()
            self.playwright = None

        self.page = None
        self._persistent_context = False
