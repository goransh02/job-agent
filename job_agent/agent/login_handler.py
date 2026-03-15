from job_agent.config import DEFAULT_EMAIL, DEFAULT_PASSWORD


def attempt_login(page):

    inputs = page.query_selector_all("input")

    email_input = None
    password_input = None

    for inp in inputs:

        name = inp.get_attribute("name") or ""

        if "email" in name.lower():
            email_input = inp

        if "password" in name.lower():
            password_input = inp

    if email_input and password_input:

        email_input.fill(DEFAULT_EMAIL)
        password_input.fill(DEFAULT_PASSWORD)

        page.keyboard.press("Enter")

        return True

    return False
