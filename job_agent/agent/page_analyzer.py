def detect_errors(page):

    errors = page.query_selector_all(".error")

    messages = []

    for e in errors:
        messages.append(e.inner_text())

    return messages
