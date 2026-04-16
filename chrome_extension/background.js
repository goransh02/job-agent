const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";
const DEFAULT_PROFILE_ID = "default";
const tabState = new Map();

function makeLogEntry(level, message, extra = {}) {
  return {
    timestamp: new Date().toISOString(),
    level,
    message,
    ...extra
  };
}

async function getStoredBackendUrl() {
  const values = await chrome.storage.local.get(["jobAgentBackendUrl", "jobAgentProfileId"]);
  return {
    backendUrl: values.jobAgentBackendUrl || DEFAULT_BACKEND_URL,
    profileId: values.jobAgentProfileId || DEFAULT_PROFILE_ID
  };
}

async function setStoredSettings({ backendUrl, profileId }) {
  const nextBackendUrl = backendUrl || DEFAULT_BACKEND_URL;
  const nextProfileId = String(profileId || DEFAULT_PROFILE_ID).trim() || DEFAULT_PROFILE_ID;
  await chrome.storage.local.set({
    jobAgentBackendUrl: nextBackendUrl,
    jobAgentProfileId: nextProfileId
  });
  return {
    backendUrl: nextBackendUrl,
    profileId: nextProfileId
  };
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

function readState(tabId) {
  return (
    tabState.get(tabId) || {
      status: "idle",
      logs: [],
      lastScan: null,
      lastPlan: null,
      pausedReason: null
    }
  );
}

function writeState(tabId, patch) {
  const next = {
    ...readState(tabId),
    ...patch
  };
  tabState.set(tabId, next);
  chrome.runtime.sendMessage({ type: "job-agent-extension.state", tabId, state: next }).catch(() => {});
  return next;
}

function appendLog(tabId, level, message, extra = {}) {
  const state = readState(tabId);
  const nextLogs = [makeLogEntry(level, message, extra), ...state.logs].slice(0, 80);
  return writeState(tabId, { logs: nextLogs });
}

async function ensureContentScript(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { type: "job-agent.ping" });
  } catch (_error) {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content-script.js"]
    });
  }
}

async function scanPage(tabId) {
  await ensureContentScript(tabId);
  return chrome.tabs.sendMessage(tabId, { type: "job-agent.scan" });
}

async function fillFields(tabId, fills) {
  return chrome.tabs.sendMessage(tabId, { type: "job-agent.fill", fills });
}

async function clickAction(tabId, actionId) {
  return chrome.tabs.sendMessage(tabId, { type: "job-agent.click-action", action_id: actionId });
}

async function resolvePlan(backendUrl, payload) {
  const response = await fetch(`${backendUrl.replace(/\/$/, "")}/api/extension/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Resolve request failed (${response.status})`);
  }

  return response.json();
}

async function saveUserValuesToProfile(backendUrl, profileId, userValues) {
  if (!userValues || Object.keys(userValues).length === 0) {
    return;
  }

  const response = await fetch(`${backendUrl.replace(/\/$/, "")}/api/extension/update-profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile_id: profileId,
      updates: userValues
    })
  });

  if (!response.ok) {
    console.warn("Failed to save user values to profile:", response.statusText);
  }
}

function hasBlockedIssues(plan, fillResult) {
  return (plan.blocked && plan.blocked.length > 0) || (fillResult.failed && fillResult.failed.length > 0);
}

function summarizeBlocked(plan, fillResult) {
  const issues = [];
  const seen = new Set();
  const addIssue = (label, reason) => {
    const text = `${label}: ${reason}`;
    if (seen.has(text)) {
      return;
    }
    seen.add(text);
    issues.push(text);
  };

  for (const blocked of plan.blocked || []) {
    addIssue(blocked.label || blocked.field_type || blocked.field_id || "field", blocked.reason);
  }
  for (const failed of fillResult.failed || []) {
    addIssue(failed.label || failed.field_id || "field", failed.reason);
  }
  return issues;
}

async function runAgent(tabId, { resumed = false, userValues = {} } = {}) {
  const { backendUrl, profileId } = await getStoredBackendUrl();
  writeState(tabId, {
    status: "running",
    pausedReason: null
  });
  appendLog(tabId, "info", resumed ? "Resuming form filler" : "Starting form filler", { backendUrl, profileId });

  // If user provided values, save them to profile and fill them in the form
  if (resumed && Object.keys(userValues).length > 0) {
    appendLog(tabId, "info", "Saving user-provided values to profile");
    await saveUserValuesToProfile(backendUrl, profileId, userValues);
    
    // Convert user values to fill format and fill them
    const userFills = Object.entries(userValues)
      .filter(([_, value]) => value && String(value).trim())
      .map(([label, value]) => ({
        label,
        value: String(value).trim()
      }));
    
    if (userFills.length > 0) {
      await fillFields(tabId, userFills);
      appendLog(tabId, "info", `Filled ${userFills.length} user-provided fields`);
    }
  }

  const scan = await scanPage(tabId);
  writeState(tabId, { lastScan: scan });
  appendLog(
    tabId,
    "info",
    "Scanned fields",
    {
      fields: (scan.fields || []).map((field) => ({
        label: field.label,
        required: field.required,
        input_type: field.input_type,
        candidates: (field.debug_candidates || []).slice(0, 5)
      }))
    }
  );

  if ((scan.fields || []).length === 0) {
    if (scan.actions?.apply?.action_id) {
      appendLog(tabId, "info", `Clicked Apply action: ${scan.actions.apply.text}`);
      await clickAction(tabId, scan.actions.apply.action_id);
      await new Promise((resolve) => setTimeout(resolve, 1200));
      return runAgent(tabId, { resumed: true });
    }

    const reason = "No visible fillable fields were detected on the page.";
    appendLog(tabId, "warn", reason, { scan });
    writeState(tabId, { status: "paused", pausedReason: reason });
    return readState(tabId);
  }

  const plan = await resolvePlan(backendUrl, {
    url: scan.url,
    fields: scan.fields,
    profile_id: profileId
  });
  writeState(tabId, { lastPlan: plan });
  appendLog(tabId, "info", `Resolved ${plan.stats.fills} fields and blocked ${plan.stats.blocked}`);

  const fillResult = await fillFields(tabId, plan.fills || []);
  appendLog(tabId, "info", `Filled ${fillResult.filled?.length || 0} fields`, fillResult);

  if (hasBlockedIssues(plan, fillResult)) {
    const issues = summarizeBlocked(plan, fillResult);
    const reason = issues.length > 0 ? issues.join(" | ") : "Manual intervention required.";
    appendLog(tabId, "warn", "Pausing because manual intervention is required", { issues });
    writeState(tabId, { status: "paused", pausedReason: reason });
    return readState(tabId);
  }

  if (scan.actions?.next?.action_id) {
    appendLog(tabId, "info", `Clicked Next action: ${scan.actions.next.text}`);
    await clickAction(tabId, scan.actions.next.action_id);
    await new Promise((resolve) => setTimeout(resolve, 1500));
    return runAgent(tabId, { resumed: true });
  }

  if (scan.actions?.submit?.action_id) {
    const reason = "Step is filled. Review the page and submit manually or press Resume after more fields load.";
    appendLog(tabId, "info", reason);
    writeState(tabId, { status: "paused", pausedReason: reason });
    return readState(tabId);
  }

  const reason = "Current visible step is filled. Review the page and press Resume when ready.";
  appendLog(tabId, "info", reason);
  writeState(tabId, { status: "paused", pausedReason: reason });
  return readState(tabId);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "job-agent-extension.get-state") {
    getActiveTab().then(async (tab) => {
      const { backendUrl, profileId } = await getStoredBackendUrl();
      sendResponse({
        ok: true,
        tabId: tab?.id || null,
        backendUrl,
        profileId,
        state: tab?.id ? readState(tab.id) : null
      });
    });
    return true;
  }

  if (message?.type === "job-agent-extension.set-backend-url") {
    setStoredSettings({
      backendUrl: message.backendUrl || DEFAULT_BACKEND_URL,
      profileId: message.profileId || DEFAULT_PROFILE_ID
    }).then(({ backendUrl, profileId }) => {
      sendResponse({ ok: true, backendUrl, profileId });
    });
    return true;
  }

  if (message?.type === "job-agent-extension.pause") {
    getActiveTab().then((tab) => {
      if (tab?.id == null) {
        sendResponse({ ok: false, message: "No active tab" });
        return;
      }
      const state = writeState(tab.id, {
        status: "paused",
        pausedReason: "Paused from the extension popup."
      });
      appendLog(tab.id, "info", "Paused from popup");
      sendResponse({ ok: true, state });
    });
    return true;
  }

  if (message?.type === "job-agent-extension.start" || message?.type === "job-agent-extension.resume") {
    getActiveTab().then((tab) => {
      if (!tab?.id || !tab.url || !/^https?:/.test(tab.url)) {
        sendResponse({ ok: false, message: "Open a normal job page tab first." });
        return;
      }
      runAgent(tab.id, { 
        resumed: message.type === "job-agent-extension.resume",
        userValues: message.userValues || {}
      })
        .then((state) => sendResponse({ ok: true, state }))
        .catch((error) => {
          appendLog(tab.id, "error", String(error));
          writeState(tab.id, {
            status: "paused",
            pausedReason: String(error)
          });
          sendResponse({ ok: false, message: String(error), state: readState(tab.id) });
        });
    });
    return true;
  }

  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  tabState.delete(tabId);
});
