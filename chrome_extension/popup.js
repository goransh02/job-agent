const backendUrlInput = document.getElementById("backendUrl");
const profileIdInput = document.getElementById("profileId");
const statusBadge = document.getElementById("statusBadge");
const pausedReason = document.getElementById("pausedReason");
const logContainer = document.getElementById("log");
const startButton = document.getElementById("startButton");
const resumeButton = document.getElementById("resumeButton");
const pauseButton = document.getElementById("pauseButton");
const refreshButton = document.getElementById("refreshButton");
const missingFieldsContainer = document.getElementById("missingFieldsContainer");
const missingFieldsInputs = document.getElementById("missingFieldsInputs");

let lastExtensionState = null;

function setStatus(status) {
  const safeStatus = status || "idle";
  statusBadge.textContent = safeStatus.charAt(0).toUpperCase() + safeStatus.slice(1);
  statusBadge.className = `badge ${safeStatus}`;
}

function parseMissingFields(logs) {
  // Look for the most recent warn log about "Pausing because manual intervention is required"
  for (const entry of logs || []) {
    if (entry.level === "warn" && entry.message && entry.message.includes("manual intervention")) {
      const issues = entry.issues || [];
      return issues.map((issue) => {
        // Parse "FieldLabel: reason" format
        const parts = issue.split(":");
        const label = parts[0]?.trim() || "";
        const reason = parts[1]?.trim() || "";
        return { label, reason, value: "" };
      });
    }
  }
  return [];
}

function renderMissingFields(fields) {
  if (!fields || fields.length === 0) {
    missingFieldsContainer.style.display = "none";
    return;
  }

  missingFieldsContainer.style.display = "block";
  missingFieldsInputs.innerHTML = fields
    .map(
      (field) =>
        `<label class="stack" style="margin-top: 8px;">
          <span>${field.label}${field.reason === "missing_value" ? " *" : ""}</span>
          <input 
            type="text" 
            class="user-field-input" 
            data-label="${field.label}"
            placeholder="Enter value"
            style="padding: 8px; border: 1px solid #ccc; border-radius: 4px;"
          >
        </label>`
    )
    .join("");
}

function collectMissingFieldValues() {
  const inputs = document.querySelectorAll(".user-field-input");
  const values = {};
  inputs.forEach((input) => {
    const label = input.dataset.label;
    values[label] = input.value.trim();
  });
  return values;
}

function renderLogs(logs) {
  const entries = logs || [];
  if (entries.length === 0) {
    logContainer.textContent = "No activity yet.";
    return;
  }

  logContainer.innerHTML = entries
    .map((entry) => {
      const timestamp = new Date(entry.timestamp).toLocaleTimeString();
      const extra = { ...entry };
      delete extra.timestamp;
      delete extra.level;
      delete extra.message;
      const extraText = Object.keys(extra).length > 0 ? `\n${JSON.stringify(extra, null, 2)}` : "";
      return `<div class="log-entry"><strong>[${timestamp}] ${entry.level}</strong>\n${entry.message}${extraText}</div>`;
    })
    .join("");
}

async function sendMessage(message) {
  return chrome.runtime.sendMessage(message);
}

async function refreshState() {
  const response = await sendMessage({ type: "job-agent-extension.get-state" });
  if (!response?.ok) {
    setStatus("idle");
    pausedReason.textContent = "Unable to load extension state.";
    renderLogs([]);
    renderMissingFields([]);
    return;
  }

  backendUrlInput.value = response.backendUrl || "";
  profileIdInput.value = response.profileId || "default";
  const state = response.state || {};
  setStatus(state.status || "idle");
  pausedReason.textContent = state.pausedReason || "Open a job page, then press Start.";
  renderLogs(state.logs || []);
  
  // Show missing fields input form if paused
  if (state.status === "paused") {
    const missingFields = parseMissingFields(state.logs);
    renderMissingFields(missingFields);
  } else {
    renderMissingFields([]);
  }
}

async function setBackendUrl() {
  const backendUrl = backendUrlInput.value.trim();
  const profileId = (profileIdInput.value || "").trim() || "default";
  await sendMessage({
    type: "job-agent-extension.set-backend-url",
    backendUrl,
    profileId
  });
}

async function runAction(type) {
  await setBackendUrl();
  const response = await sendMessage({ type });
  if (!response?.ok && response?.message) {
    pausedReason.textContent = response.message;
  }
  await refreshState();
}

backendUrlInput.addEventListener("change", async () => {
  await setBackendUrl();
  await refreshState();
});
profileIdInput.addEventListener("change", async () => {
  await setBackendUrl();
  await refreshState();
});
startButton.addEventListener("click", () => runAction("job-agent-extension.start"));
resumeButton.addEventListener("click", async () => {
  // Collect user-provided values for missing fields
  const userValues = collectMissingFieldValues();
  await setBackendUrl();
  const response = await sendMessage({ 
    type: "job-agent-extension.resume",
    userValues: userValues
  });
  if (!response?.ok && response?.message) {
    pausedReason.textContent = response.message;
  }
  await refreshState();
});
pauseButton.addEventListener("click", () => runAction("job-agent-extension.pause"));
refreshButton.addEventListener("click", refreshState);

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "job-agent-extension.state") {
    refreshState();
  }
});

refreshState();
