async def accept_cookies(page):
    buttons = await page.query_selector_all("button")

    for button in buttons:
        try:
            text = ((await button.inner_text()) or "").lower()
        except Exception:
            continue

        if "accept" in text or "agree" in text:
            try:
                await button.click()
                return True
            except Exception:
                continue

    return False
