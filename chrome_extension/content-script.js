const JOB_AGENT_FIELD_ATTR = "data-job-agent-field-id";
const JOB_AGENT_ACTION_ATTR = "data-job-agent-action-id";

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizedLower(value) {
  return normalizeText(value).toLowerCase();
}

function isVisible(element) {
  if (!element || !(element instanceof Element)) {
    return false;
  }

  const style = window.getComputedStyle(element);
  if (
    style.display === "none" ||
    style.visibility === "hidden" ||
    style.opacity === "0"
  ) {
    return false;
  }

  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function ensureDataId(element, attrName, prefix) {
  let value = element.getAttribute(attrName);
  if (value) {
    return value;
  }

  value = `${prefix}-${crypto.randomUUID()}`;
  element.setAttribute(attrName, value);
  return value;
}

function hasUsefulAlpha(text) {
  return /[a-z]/i.test(text || "");
}

function normalizeLabelText(value) {
  return normalizeText(value).replace(/\s+/g, " ").trim();
}

function splitLabelFragments(value) {
  return String(value || "")
    .split(/\n|[|]/)
    .map((part) => normalizeLabelText(part))
    .filter(Boolean);
}

function isPoorLabelText(value) {
  const normalized = normalizedLower(value);
  if (!normalized) {
    return true;
  }

  if (/^[0-9*.\-()]+$/.test(normalized)) {
    return true;
  }

  if (normalized.length < 2) {
    return true;
  }

  if (!hasUsefulAlpha(normalized) && !normalized.includes("@")) {
    return true;
  }

  if (["choose file", "no file chosen", "browse"].includes(normalized)) {
    return true;
  }

  if (["your details", "about you", "permanent - full time", "engineering"].includes(normalized)) {
    return true;
  }

  return false;
}

function labelKeywordBonus(value) {
  const normalized = normalizedLower(value);
  if (
    /(name|email|phone|mobile|location|address|city|state|country|linkedin|github|portfolio|website|social|resume|cv|cover letter|experience|title|company|notice|profile|summary|about)/.test(normalized)
  ) {
    return 70;
  }
  return 0;
}

function scoreLabelCandidate(text, baseScore) {
  let score = baseScore;
  const normalized = normalizedLower(text);

  if (isPoorLabelText(normalized)) {
    return -1000;
  }

  if (/^\d+\s+/.test(normalized)) {
    score -= 180;
  }

  if (normalized.length > 120) {
    score -= 120;
  }

  score += labelKeywordBonus(normalized);
  return score;
}

function collectLabelCandidates(element) {
  const candidateMap = new Map();
  const push = (value, baseScore) => {
    for (const cleaned of splitLabelFragments(value)) {
      const score = scoreLabelCandidate(cleaned, baseScore);
      if (score <= 0) {
        continue;
      }

      const existing = candidateMap.get(cleaned);
      if (!existing || score > existing.score) {
        candidateMap.set(cleaned, { text: cleaned, score });
      }
    }
  };

  const collectContainerOwnText = (container) => {
    if (!container) {
      return [];
    }

    const fragments = [];
    for (const node of container.childNodes) {
      if (node === element) {
        continue;
      }

      if (node.nodeType === Node.TEXT_NODE) {
        fragments.push(...splitLabelFragments(node.textContent || ""));
        continue;
      }

      if (!(node instanceof Element)) {
        continue;
      }

      if (node === element || node.contains(element)) {
        continue;
      }

      if (!isVisible(node)) {
        continue;
      }

      const tagName = node.tagName.toLowerCase();
      if (["input", "textarea", "select", "button"].includes(tagName)) {
        continue;
      }

      fragments.push(...splitLabelFragments(node.innerText || node.textContent || ""));
    }

    return fragments;
  };

  const addNearbyCandidate = (candidate, baseScore, elementRect) => {
    if (!candidate || candidate === element || candidate.contains(element) || !isVisible(candidate)) {
      return;
    }

    const text = normalizeLabelText(candidate.innerText || candidate.textContent);
    if (!text) {
      return;
    }

    const candidateRect = candidate.getBoundingClientRect();
    let score = baseScore;
    const tagName = candidate.tagName.toLowerCase();

    if (["label", "legend", "strong"].includes(tagName)) {
      score += 80;
    }

    if (candidateRect.bottom <= elementRect.top + 24) {
      score += 70;
    }

    if (candidateRect.left <= elementRect.left + 12) {
      score += 40;
    }

    if (candidateRect.left <= elementRect.right && candidateRect.right >= elementRect.left) {
      score += 40;
    }

    const verticalDistance = Math.abs(elementRect.top - candidateRect.bottom);
    score += Math.max(0, 70 - Math.min(verticalDistance, 70));

    push(text, score);
  };

  push(element.getAttribute("aria-label"), 220);
  push(element.getAttribute("placeholder"), 160);
  push(element.getAttribute("name"), 100);

  if (element.id) {
    const explicitLabel = document.querySelector(`label[for="${CSS.escape(element.id)}"]`);
    if (explicitLabel) {
      push(explicitLabel.innerText || explicitLabel.textContent, 320);
    }
  }

  if (element.labels) {
    for (const label of element.labels) {
      push(label.innerText || label.textContent, 320);
    }
  }

  const closestLabel = element.closest("label");
  if (closestLabel) {
    push(closestLabel.innerText || closestLabel.textContent, 300);
  }

  const elementRect = element.getBoundingClientRect();
  let sibling = element.previousElementSibling;
  let siblingDepth = 0;
  while (sibling && siblingDepth < 4) {
    addNearbyCandidate(sibling, 260 - siblingDepth * 30, elementRect);
    sibling = sibling.previousElementSibling;
    siblingDepth += 1;
  }

  const parent = element.parentElement;
  if (parent) {
    for (const fragment of collectContainerOwnText(parent)) {
      push(fragment, 260);
    }
    for (const candidate of Array.from(parent.children)) {
      addNearbyCandidate(candidate, 210, elementRect);
    }
  }

  let current = element.parentElement;
  for (let depth = 0; current && depth < 4; depth += 1) {
    for (const fragment of collectContainerOwnText(current)) {
      push(fragment, 230 - depth * 30);
    }
    const scoped = current.querySelectorAll("label, legend, span, div, p, strong");
    for (const candidate of scoped) {
      addNearbyCandidate(candidate, 160 - depth * 25, elementRect);
    }
    current = current.parentElement;
  }

  return Array.from(candidateMap.values());
}

function pickBestLabel(element) {
  const candidates = collectLabelCandidates(element);
  if (candidates.length === 0) {
    return "";
  }

  const requiredHint = element.required || element.getAttribute("aria-required") === "true";
  const best = candidates.sort((left, right) => {
    if (right.score !== left.score) {
      return right.score - left.score;
    }
    return left.text.length - right.text.length;
  })[0].text;
  return requiredHint && !best.includes("*") ? `${best}*` : best;
}

function readOptions(element) {
  if (element.tagName.toLowerCase() === "select") {
    return Array.from(element.options || []).map((option) => normalizeText(option.textContent || option.label || option.value));
  }
  return [];
}

function isFieldElement(element) {
  const tagName = element.tagName.toLowerCase();
  const inputType = normalizedLower(element.getAttribute("type"));
  const role = normalizedLower(element.getAttribute("role"));

  if (!isVisible(element) || element.disabled) {
    return false;
  }

  if (tagName === "textarea" || tagName === "select") {
    return true;
  }

  if (tagName === "input") {
    if (["hidden", "button", "submit", "reset", "image"].includes(inputType)) {
      return false;
    }
    return true;
  }

  return role === "combobox";
}

function scoreAction(text, kind) {
  const normalized = normalizedLower(text);
  if (!normalized) {
    return -100;
  }

  if (kind === "apply") {
    if (/(linkedin|dropbox|google drive|onedrive|register|sign up|sign in|log in)/.test(normalized)) {
      return -200;
    }
    if (/apply manually/.test(normalized)) {
      return 260;
    }
    if (/apply now|apply for this job/.test(normalized)) {
      return 220;
    }
    if (/apply/.test(normalized)) {
      return 200;
    }
    return -100;
  }

  if (kind === "next") {
    if (/(submit|sign in|log in)/.test(normalized)) {
      return -200;
    }
    if (/save and continue/.test(normalized)) {
      return 240;
    }
    if (/continue/.test(normalized)) {
      return 180;
    }
    if (/next/.test(normalized)) {
      return 260;
    }
    if (/review/.test(normalized)) {
      return 150;
    }
    return -100;
  }

  if (kind === "submit") {
    if (/submit/.test(normalized)) {
      return 260;
    }
    if (/review/.test(normalized)) {
      return 180;
    }
  }

  return -100;
}

function gatherActions() {
  const actions = {
    apply: null,
    next: null,
    submit: null
  };

  const candidates = document.querySelectorAll("button, a, input[type='button'], input[type='submit'], [role='button']");
  for (const element of candidates) {
    if (!isVisible(element)) {
      continue;
    }

    const text = normalizeText(
      element.innerText ||
        element.textContent ||
        element.getAttribute("value") ||
        element.getAttribute("aria-label") ||
        ""
    );
    if (!text) {
      continue;
    }

    const actionId = ensureDataId(element, JOB_AGENT_ACTION_ATTR, "action");
    for (const kind of ["apply", "next", "submit"]) {
      const score = scoreAction(text, kind);
      if (score <= 0) {
        continue;
      }

      if (!actions[kind] || score > actions[kind].score) {
        actions[kind] = {
          action_id: actionId,
          text,
          score
        };
      }
    }
  }

  return actions;
}

function scanFields() {
  const selectors = "input, textarea, select, [role='combobox']";
  const seen = new Set();
  const fields = [];

  for (const element of document.querySelectorAll(selectors)) {
    if (!isFieldElement(element)) {
      continue;
    }

    const fieldId = ensureDataId(element, JOB_AGENT_FIELD_ATTR, "field");
    if (seen.has(fieldId)) {
      continue;
    }
    seen.add(fieldId);

    const tagName = element.tagName.toLowerCase();
    const role = normalizedLower(element.getAttribute("role"));
    const inputType = normalizedLower(element.getAttribute("type"));
    const field = {
      field_id: fieldId,
      label: pickBestLabel(element),
      tag_name: tagName,
      input_type: inputType,
      role,
      required: Boolean(element.required || element.getAttribute("aria-required") === "true"),
      options: readOptions(element),
      debug_candidates: collectLabelCandidates(element)
    };
    fields.push(field);
  }

  return fields;
}

function isTruthyValue(value) {
  const normalized = normalizedLower(value);
  return ["1", "true", "yes", "y", "checked", "on", "mobile", "current"].includes(normalized);
}

function dispatchInputEvents(element) {
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true }));
}

function setTextValue(element, value) {
  element.focus();
  element.value = value;
  dispatchInputEvents(element);
}

function setCheckboxValue(element, value) {
  const checked = isTruthyValue(value);
  element.checked = checked;
  dispatchInputEvents(element);
}

function selectBestOption(element, value) {
  const target = normalizedLower(value);
  const options = Array.from(element.options || []);

  let winner = null;
  let winnerScore = -1;

  for (const option of options) {
    const optionText = normalizedLower(option.textContent || option.label || option.value);
    const optionValue = normalizedLower(option.value);
    let score = 0;
    if (optionText === target || optionValue === target) {
      score = 300;
    } else if (target && (optionText.includes(target) || target.includes(optionText))) {
      score = 180;
    }
    if (score > winnerScore) {
      winner = option;
      winnerScore = score;
    }
  }

  if (!winner) {
    return false;
  }

  element.value = winner.value;
  dispatchInputEvents(element);
  return true;
}

function findVisibleOption(value) {
  const target = normalizedLower(value);
  const options = document.querySelectorAll("[role='option'], li[role='option'], li, div");
  let winner = null;
  let winnerScore = -1;

  for (const option of options) {
    if (!isVisible(option)) {
      continue;
    }
    const text = normalizedLower(option.innerText || option.textContent);
    if (!text || text.length > 100) {
      continue;
    }
    let score = 0;
    if (text === target) {
      score = 300;
    } else if (target && (text.includes(target) || target.includes(text))) {
      score = 180;
    }
    if (score > winnerScore) {
      winner = option;
      winnerScore = score;
    }
  }

  return winner;
}

async function fillCombobox(element, value) {
  element.scrollIntoView({ block: "center" });
  element.click();

  if (typeof element.value === "string") {
    setTextValue(element, value);
  } else {
    const input = element.querySelector("input") || document.activeElement;
    if (input && input instanceof HTMLInputElement) {
      setTextValue(input, value);
    }
  }

  await new Promise((resolve) => window.setTimeout(resolve, 200));
  const option = findVisibleOption(value);
  if (option) {
    option.click();
    return true;
  }

  const active = document.activeElement;
  if (active && typeof active.dispatchEvent === "function") {
    active.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    active.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  }

  return true;
}

async function applyFill(plan) {
  const filled = [];
  const failed = [];

  for (const item of plan || []) {
    let element = null;
    let matchedLabel = null;
    
    // First try to find by field_id
    if (item.field_id) {
      const selector = `[${JOB_AGENT_FIELD_ATTR}="${CSS.escape(item.field_id)}"]`;
      element = document.querySelector(selector);
    }
    
    // If not found and we have a label, try to find by scanning fields and matching label
    if (!element && item.label) {
      const scannedFields = scanFields();
      for (const field of scannedFields) {
        if (normalizedLower(field.label) === normalizedLower(item.label)) {
          matchedLabel = field.label;
          const selector = `[${JOB_AGENT_FIELD_ATTR}="${CSS.escape(field.field_id)}"]`;
          element = document.querySelector(selector);
          break;
        }
      }
    }
    
    if (!element) {
      const identifier = item.field_id || item.label || "unknown";
      failed.push({ field_id: item.field_id, label: item.label, reason: "element_not_found" });
      continue;
    }

    try {
      const tagName = element.tagName.toLowerCase();
      const inputType = normalizedLower(element.getAttribute("type"));
      const role = normalizedLower(element.getAttribute("role"));

      if (inputType === "file") {
        failed.push({ field_id: item.field_id, label: item.label, reason: "file_upload_manual" });
        continue;
      }

      if (tagName === "select") {
        if (!selectBestOption(element, item.value)) {
          failed.push({ field_id: item.field_id, label: item.label, reason: "option_not_found" });
          continue;
        }
      } else if (["checkbox", "radio"].includes(inputType)) {
        setCheckboxValue(element, item.value);
      } else if (role === "combobox") {
        await fillCombobox(element, item.value);
      } else {
        setTextValue(element, item.value);
      }

      filled.push({ field_id: item.field_id, label: item.label, value: item.value });
    } catch (error) {
      failed.push({ field_id: item.field_id, label: item.label, reason: String(error) });
    }
  }

  return { filled, failed };
}

async function clickAction(actionId) {
  const selector = `[${JOB_AGENT_ACTION_ATTR}="${CSS.escape(actionId)}"]`;
  const element = document.querySelector(selector);
  if (!element) {
    return { clicked: false, reason: "action_not_found" };
  }

  element.scrollIntoView({ block: "center" });
  element.click();
  return { clicked: true };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "job-agent.ping") {
    sendResponse({ ok: true });
    return false;
  }

  if (message?.type === "job-agent.scan") {
    sendResponse({
      url: window.location.href,
      title: document.title,
      fields: scanFields(),
      actions: gatherActions()
    });
    return false;
  }

  if (message?.type === "job-agent.fill") {
    applyFill(message.fills || []).then(sendResponse);
    return true;
  }

  if (message?.type === "job-agent.click-action") {
    clickAction(message.action_id).then(sendResponse);
    return true;
  }

  return false;
});
