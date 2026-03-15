from __future__ import annotations


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


def _clean(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _label_for_element(page, element):
    element_id = _clean(element.get_attribute("id"))
    if element_id:
        label = page.query_selector(f'label[for="{element_id}"]')
        if label is not None:
            text = _clean(label.inner_text())
            if text:
                return text

    candidates = (
        element.get_attribute("aria-label"),
        element.get_attribute("placeholder"),
        element.get_attribute("name"),
        element.get_attribute("data-automation-id"),
        element.get_attribute("id"),
    )

    for candidate in candidates:
        cleaned = _clean(candidate)
        if cleaned:
            return cleaned

    return None


def parse_fields(page):
    fields = []
    seen = set()

    for element in page.query_selector_all("input, textarea, select"):
        input_type = (element.get_attribute("type") or "").lower()
        if input_type in SKIP_INPUT_TYPES:
            continue

        label = _label_for_element(page, element)
        if not label:
            continue

        signature = (
            label,
            element.get_attribute("name") or "",
            element.get_attribute("id") or "",
        )
        if signature in seen:
            continue

        seen.add(signature)
        fields.append(
            {
                "label": label,
                "element": element,
                "input_type": input_type,
            }
        )

    return fields
