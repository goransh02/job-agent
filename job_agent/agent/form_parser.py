from __future__ import annotations

FORM_FIELD_SELECTOR = (
    "input, textarea, select, "
    '[role="combobox"], '
    'input[role="combobox"], '
    'button[aria-haspopup="listbox"], '
    '[aria-haspopup="listbox"]'
)

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


def _is_detached_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "frame was detached" in message
        or "execution context was destroyed" in message
        or "element is not attached" in message
        or "target page, context or browser has been closed" in message
        or "browser has been closed" in message
    )


def _iter_scopes(page_or_frame):
    frames = getattr(page_or_frame, "frames", None)
    if frames is None:
        return [page_or_frame]
    return list(frames)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(value.split()).strip()
    return cleaned or None


async def _label_from_aria_labelledby(page, element):
    labelledby = _clean(await element.get_attribute("aria-labelledby"))
    if not labelledby:
        return None

    parts = []
    for label_id in labelledby.split():
        target = await page.query_selector(f'#{label_id}')
        if target is None:
            continue

        text = _clean(await target.inner_text())
        if text:
            parts.append(text)

    if not parts:
        return None

    return " ".join(parts)


async def _label_from_dom_context(element):
    try:
        text = await element.evaluate(
            """(node) => {
                const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
                const acceptable = (value) => {
                    if (!value) return false;
                    if (value.length < 2 || value.length > 80) return false;
                    if (!/[a-zA-Z]/.test(value)) return false;
                    const normalized = value.toLowerCase();
                    if (normalized === "required" || normalized === "*") return false;
                    if (normalized.includes("error -")) return false;
                    return true;
                };

                if (node.labels && node.labels.length) {
                    for (const label of node.labels) {
                        const text = clean(label.innerText || label.textContent || "");
                        if (acceptable(text)) return text;
                    }
                }

                const directLabel = node.closest("label");
                if (directLabel) {
                    const text = clean(directLabel.innerText || directLabel.textContent || "");
                    if (acceptable(text)) return text;
                }

                const nodeRect = typeof node.getBoundingClientRect === "function"
                    ? node.getBoundingClientRect()
                    : null;

                const nearbyText = (container) => {
                    if (!container) return null;
                    const walker = document.createTreeWalker(container, NodeFilter.SHOW_ELEMENT);
                    let best = null;

                    while (walker.nextNode()) {
                        const candidate = walker.currentNode;
                        if (candidate === node || candidate.contains(node) || node.contains(candidate)) {
                            continue;
                        }

                        const text = clean(candidate.innerText || candidate.textContent || "");
                        if (!acceptable(text)) continue;

                        if (!nodeRect || typeof candidate.getBoundingClientRect !== "function") {
                            return text;
                        }

                        const rect = candidate.getBoundingClientRect();
                        const verticalDistance = Math.abs(rect.bottom - nodeRect.top);
                        const horizontalOverlap = Math.min(rect.right, nodeRect.right) - Math.max(rect.left, nodeRect.left);

                        if (horizontalOverlap < -12) continue;
                        if (rect.bottom > nodeRect.top + 12) continue;

                        const score = verticalDistance + Math.max(0, -horizontalOverlap);
                        if (!best || score < best.score) {
                            best = { score, text };
                        }
                    }

                    return best ? best.text : null;
                };

                let container = node.parentElement;
                for (let depth = 0; container && depth < 4; depth += 1) {
                    const text = nearbyText(container);
                    if (acceptable(text)) return text;
                    container = container.parentElement;
                }

                let current = node;
                for (let depth = 0; current && depth < 4; depth += 1) {
                    let sibling = current.previousElementSibling;
                    while (sibling) {
                        const text = clean(sibling.innerText || sibling.textContent || "");
                        if (acceptable(text)) return text;
                        sibling = sibling.previousElementSibling;
                    }
                    current = current.parentElement;
                }

                current = node.parentElement;
                for (let depth = 0; current && depth < 3; depth += 1) {
                    for (const child of current.children) {
                        if (child === node || child.contains(node)) continue;
                        const text = clean(child.innerText || child.textContent || "");
                        if (acceptable(text)) return text;
                    }
                    current = current.parentElement;
                }

                return null;
            }"""
        )
    except Exception:
        return None

    return _clean(text)


async def _label_for_element(page, element):
    element_id = _clean(await element.get_attribute("id"))
    if element_id:
        label = await page.query_selector(f'label[for="{element_id}"]')
        if label is not None:
            text = _clean(await label.inner_text())
            if text:
                return text

    labelledby_text = await _label_from_aria_labelledby(page, element)
    if labelledby_text:
        return labelledby_text

    candidates = (
        await element.get_attribute("aria-label"),
        await element.get_attribute("placeholder"),
        await element.get_attribute("name"),
        await element.get_attribute("data-automation-id"),
        await element.get_attribute("id"),
    )

    for candidate in candidates:
        cleaned = _clean(candidate)
        if cleaned:
            return cleaned

    contextual_label = await _label_from_dom_context(element)
    if contextual_label:
        return contextual_label

    return None


async def _is_visible(element) -> bool:
    try:
        return await element.is_visible()
    except Exception:
        return True


async def parse_fields(page_or_frame):
    fields = []
    seen = set()

    for scope in _iter_scopes(page_or_frame):
        try:
            elements = await scope.query_selector_all(FORM_FIELD_SELECTOR)
        except Exception as exc:
            if _is_detached_error(exc):
                continue
            raise

        for element in elements:
            if not await _is_visible(element):
                continue

            try:
                tag_name = ((await element.evaluate("(node) => node.tagName.toLowerCase()")) or "").lower()
                role = ((await element.get_attribute("role")) or "").lower()
                has_popup = ((await element.get_attribute("aria-haspopup")) or "").lower()
            except Exception as exc:
                if _is_detached_error(exc):
                    continue
                raise

            input_type = ""
            if tag_name == "input":
                try:
                    input_type = ((await element.get_attribute("type")) or "").lower()
                except Exception as exc:
                    if _is_detached_error(exc):
                        continue
                    raise
                if input_type in SKIP_INPUT_TYPES:
                    continue

            if tag_name in {"button", "div"} and role != "combobox" and has_popup != "listbox":
                continue

            try:
                label = await _label_for_element(scope, element)
            except Exception as exc:
                if _is_detached_error(exc):
                    continue
                raise
            if not label:
                continue

            try:
                signature = (
                    getattr(scope, "url", "") or "",
                    label,
                    tag_name,
                    await element.get_attribute("name") or "",
                    await element.get_attribute("id") or "",
                )
            except Exception as exc:
                if _is_detached_error(exc):
                    continue
                raise
            if signature in seen:
                continue

            seen.add(signature)
            fields.append(
                {
                    "label": label,
                    "element": element,
                    "input_type": input_type,
                    "tag_name": tag_name,
                    "role": role,
                    "scope_url": getattr(scope, "url", "") or "",
                }
            )

    return fields
