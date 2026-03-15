def accept_cookies(page):

    buttons = page.query_selector_all("button")

    for b in buttons:

        text = b.inner_text().lower()

        if "accept" in text or "agree" in text:

            try:
                b.click()
                return True
            except:
                pass

    return False
