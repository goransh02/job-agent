const connectButton = document.getElementById("connectButton");
const startButton = document.getElementById("startButton");
const continueButton = document.getElementById("continueButton");
const clearLogButton = document.getElementById("clearLogButton");
const refreshResumeButton = document.getElementById("refreshResumeButton");
const resumeForm = document.getElementById("resumeForm");
const resumeFile = document.getElementById("resumeFile");
const resumeStatus = document.getElementById("resumeStatus");
const resumeMeta = document.getElementById("resumeMeta");
const socketState = document.getElementById("socketState");
const runState = document.getElementById("runState");
const eventLog = document.getElementById("eventLog");
const jobUrlInput = document.getElementById("jobUrl");
const profileIdInput = document.getElementById("profileId");
const questionField = document.getElementById("questionField");
const questionState = document.getElementById("questionState");
const answerForm = document.getElementById("answerForm");
const answerInput = document.getElementById("answerInput");
const sendAnswerButton = document.getElementById("sendAnswerButton");

let socket = null;
let pendingQuestion = null;
let activeApplicationId = null;

function currentProfileId() {
  return (profileIdInput?.value || "").trim() || "default";
}

function setRunState(label, stateClass) {
  runState.textContent = label;
  runState.className = `socket-state ${stateClass}`;
}

function appendLog(kind, payload) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  const timestamp = new Date().toLocaleTimeString();
  const text = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
  entry.innerHTML = `<strong>[${timestamp}] ${kind}</strong>\n${text}`;
  eventLog.prepend(entry);
}

function setSocketState(label, stateClass) {
  socketState.textContent = label;
  socketState.className = `socket-state ${stateClass}`;
}

function setQuestionState(label, stateClass) {
  questionState.textContent = label;
  questionState.className = `socket-state ${stateClass}`;
}

function setPendingQuestion(question) {
  pendingQuestion = question;
  if (!question) {
    questionField.textContent = "No question pending.";
    answerInput.value = "";
    answerInput.disabled = true;
    sendAnswerButton.disabled = true;
    setQuestionState("None", "idle");
    return;
  }

  questionField.textContent = question;
  answerInput.disabled = false;
  sendAnswerButton.disabled = false;
  answerInput.focus();
  setQuestionState("Waiting", "waiting");
}

function buildWsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/agent`;
}

function connectSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    appendLog("ui", "WebSocket is already active.");
    return;
  }

  setSocketState("Connecting", "waiting");
  socket = new WebSocket(buildWsUrl());

  socket.onopen = () => {
    setSocketState("Connected", "connected");
    setRunState("Idle", "idle");
    appendLog("socket", "Connected to /agent");
  };

  socket.onclose = () => {
    setSocketState("Disconnected", "idle");
    setRunState("Idle", "idle");
    activeApplicationId = null;
    appendLog("socket", "Connection closed");
  };

  socket.onerror = () => {
    appendLog("error", "WebSocket error occurred.");
  };

  socket.onmessage = (event) => {
    let payload = event.data;
    try {
      payload = JSON.parse(event.data);
    } catch (error) {
      appendLog("message", event.data);
      return;
    }

    appendLog(payload.type || "message", payload);

    if (payload.type === "question") {
      setRunState("Waiting", "waiting");
      setPendingQuestion(payload.field || "Unknown question");
      return;
    }

    if (payload.type === "paused") {
      setRunState("Paused", "waiting");
      activeApplicationId = payload.result?.application_id || activeApplicationId;
      setPendingQuestion(null);
      return;
    }

    if (payload.type === "complete") {
      setRunState("Complete", "connected");
      activeApplicationId = payload.result?.application_id || activeApplicationId;
      setPendingQuestion(null);
      return;
    }

    if (payload.type === "error") {
      setRunState("Error", "idle");
      setPendingQuestion(null);
      return;
    }
  };
}

async function refreshResume() {
  resumeStatus.textContent = "Loading resume metadata...";
  resumeMeta.innerHTML = "";

  try {
    const response = await fetch(`/api/profile/resume?profile_id=${encodeURIComponent(currentProfileId())}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      resumeStatus.textContent = body.detail || "No resume stored yet.";
      return;
    }

    const payload = await response.json();
    resumeStatus.textContent = "Stored resume is ready for autofill/upload flows.";
    resumeMeta.innerHTML = `
      <dt>File</dt><dd>${payload.resume_filename || "Unknown"}</dd>
      <dt>Size</dt><dd>${payload.resume_size_bytes || 0} bytes</dd>
      <dt>Content-Type</dt><dd>${payload.resume_content_type || "Unknown"}</dd>
      <dt>ID</dt><dd>${payload.resume_file_id || "Unknown"}</dd>
    `;
  } catch (error) {
    resumeStatus.textContent = "Unable to load resume metadata.";
    appendLog("error", String(error));
  }
}

async function uploadResume(event) {
  event.preventDefault();

  if (!resumeFile.files || resumeFile.files.length === 0) {
    resumeStatus.textContent = "Choose a file before uploading.";
    return;
  }

  const formData = new FormData();
  formData.append("file", resumeFile.files[0]);
  resumeStatus.textContent = "Uploading resume...";

  try {
    const response = await fetch(`/api/profile/resume?profile_id=${encodeURIComponent(currentProfileId())}`, {
      method: "POST",
      body: formData
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      resumeStatus.textContent = payload.detail || "Upload failed.";
      appendLog("error", payload);
      return;
    }

    resumeStatus.textContent = payload.message || "Resume uploaded.";
    appendLog("resume", payload);
    resumeFile.value = "";
    await refreshResume();
  } catch (error) {
    resumeStatus.textContent = "Upload failed.";
    appendLog("error", String(error));
  }
}

function startRun() {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    appendLog("ui", "Connect the WebSocket before starting a run.");
    return;
  }

  const url = jobUrlInput.value.trim();
  if (!url) {
    appendLog("ui", "Enter a job URL first.");
    return;
  }

  const payload = { type: "start", url, profile_id: currentProfileId() };
  activeApplicationId = null;
  setRunState("Running", "connected");
  socket.send(JSON.stringify(payload));
  appendLog("send", payload);
}

function continueRun() {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    appendLog("ui", "Connect the WebSocket before continuing a run.");
    return;
  }

  const payload = {
    type: "continue",
    profile_id: currentProfileId(),
    application_id: activeApplicationId
  };
  setRunState("Running", "connected");
  socket.send(JSON.stringify(payload));
  appendLog("send", payload);
}

function sendAnswer(event) {
  event.preventDefault();

  if (!socket || socket.readyState !== WebSocket.OPEN) {
    appendLog("ui", "Socket is not connected.");
    return;
  }

  const answer = answerInput.value.trim();
  if (!answer) {
    appendLog("ui", "Type an answer before sending.");
    return;
  }

  const payload = { answer };
  socket.send(JSON.stringify(payload));
  appendLog("send", payload);
  setPendingQuestion(null);
}

connectButton.addEventListener("click", connectSocket);
startButton.addEventListener("click", startRun);
continueButton.addEventListener("click", continueRun);
clearLogButton.addEventListener("click", () => {
  eventLog.innerHTML = "";
});
refreshResumeButton.addEventListener("click", refreshResume);
resumeForm.addEventListener("submit", uploadResume);
answerForm.addEventListener("submit", sendAnswer);

jobUrlInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    startRun();
  }
});

refreshResume();
setRunState("Idle", "idle");
profileIdInput.addEventListener("change", refreshResume);
