async def detect_errors(page):
    errors = await page.query_selector_all(".error")

    messages = []

    for error in errors:
        messages.append(await error.inner_text())

    return messages
