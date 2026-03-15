from job_agent.config import DEFAULT_EMAIL, DEFAULT_PASSWORD


def attempt_register(page):

    inputs = page.query_selector_all("input")

    for inp in inputs:

        label = inp.get_attribute("name") or ""

        if "email" in label.lower():
            inp.fill(DEFAULT_EMAIL)

        if "password" in label.lower():
            inp.fill(DEFAULT_PASSWORD)
