from __future__ import annotations

import argparse
import asyncio

from job_agent.browser.playwright_browser import Browser


async def main() -> int:
    parser = argparse.ArgumentParser(description="Open a URL with Playwright for smoke testing.")
    parser.add_argument("url", help="URL to open")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--persistent",
        action="store_true",
        help="Launch with a persistent browser profile",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Browser user data directory for persistent mode",
    )
    parser.add_argument(
        "--channel",
        default=None,
        help="Browser channel, for example chrome",
    )
    parser.add_argument(
        "--cdp-url",
        default=None,
        help="Attach to an existing browser over CDP instead of launching a fresh one",
    )
    parser.add_argument(
        "--new-window",
        action="store_true",
        help="When using CDP attach, request a real new Chrome window instead of a new tab",
    )
    args = parser.parse_args()

    browser = Browser(
        headless=args.headless,
        use_persistent_context=args.persistent,
        user_data_dir=args.user_data_dir,
        browser_channel=args.channel,
        cdp_url=args.cdp_url,
        cdp_new_window=args.new_window,
    )

    try:
        await browser.open(args.url)
        print(f"Opened: {browser.page.url}", flush=True)
        print("Press Enter to close the browser...", flush=True)
        await asyncio.to_thread(input)
        return 0
    finally:
        await browser.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
