const backendUrlInput = document.getElementById("backendUrl");
const profileIdInput = document.getElementById("profileId");
const statusBadge = document.getElementById("statusBadge");
const pausedReason = document.getElementById("pausedReason");
const logContainer = document.getElementById("log");
const startButton = document.getElementById("startButton");
const resumeButton = document.getElementById("resumeButton");
const pauseButton = document.getElementById("pauseButton");
const refreshButton = document.getElementById("refreshButton");

function setStatus(status) {
  const safeStatus = status || "idle";
  statusBadge.textContent = safeStatus.charAt(0).toUpperCase() + safeStatus.slice(1);
  statusBadge.className = `badge ${safeStatus}`;
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
    return;
  }

  backendUrlInput.value = response.backendUrl || "";
  profileIdInput.value = response.profileId || "default";
  const state = response.state || {};
  setStatus(state.status || "idle");
  pausedReason.textContent = state.pausedReason || "Open a job page, then press Start.";
  renderLogs(state.logs || []);
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
resumeButton.addEventListener("click", () => runAction("job-agent-extension.resume"));
pauseButton.addEventListener("click", () => runAction("job-agent-extension.pause"));
refreshButton.addEventListener("click", refreshState);

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "job-agent-extension.state") {
    refreshState();
  }
});

refreshState();
