from job_agent.config import DEFAULT_EMAIL, DEFAULT_PASSWORD
from job_agent.services.profile_service import get_profile, normalize_profile_id


def _best_email(profile_id: str | None = None) -> str:
    profile = get_profile(normalize_profile_id(profile_id))
    return (profile.get("email") or DEFAULT_EMAIL or "").strip()


async def _field_hint(inp) -> str:
    parts = []
    for attr in ("name", "id", "placeholder", "aria-label", "autocomplete"):
        try:
            value = await inp.get_attribute(attr)
        except Exception:
            value = None
        if value:
            parts.append(value)
    return " ".join(parts).lower()


async def attempt_register(page, profile_id: str | None = None):
    inputs = await page.query_selector_all("input")
    email_value = _best_email(profile_id)
    password_value = (DEFAULT_PASSWORD or "").strip()
    filled_any = False

    for inp in inputs:
        hint = await _field_hint(inp)
        input_type = ((await inp.get_attribute("type")) or "").lower()

        if input_type in {"email", "text"} and any(token in hint for token in ("email", "username", "login")) and email_value:
            await inp.fill(email_value)
            filled_any = True

        if (input_type == "password" or "password" in hint) and password_value:
            await inp.fill(password_value)
            filled_any = True

    return filled_any
