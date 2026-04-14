# Job Agent

This project is a job-application assistant built around FastAPI, Playwright, profile data, Groq-backed resume reasoning, and a LangGraph application runner.

## Current defaults

The app now starts in a safe, lightweight mode:

- Browser runs headless by default.
- Auto-submit is off by default.
- Mongo falls back to in-memory storage if it is unavailable.
- Transformer embeddings are off by default.
- Ollama fallback is off by default.
- Groq chunking/reasoning is off until you provide an API key.

That means you can run tests and most app logic without immediately loading heavy local models.

## Install

```bash
python3 -m pip install -r job_agent/requirements.txt
playwright install chromium
```

## Configure

Copy `.env.example` to `.env` and set the values you need.

New graph/retrieval settings:

```env
JOB_AGENT_DEFAULT_PROFILE_ID=default
JOB_AGENT_GROQ_API_KEY=
JOB_AGENT_GROQ_CHUNK_MODEL=llama-3.1-8b-instant
JOB_AGENT_GROQ_REASONING_MODEL=llama-3.3-70b-versatile
```

Recommended lightweight local LLM options for Ollama:

- `llama3.2:1b`
- `qwen2.5:1.5b`
- `phi3:mini`

Keep this disabled until the rest of the flow is stable:

```env
JOB_AGENT_ENABLE_LLM_FALLBACK=false
```

When you want to try local LLM fallback again:

```env
JOB_AGENT_ENABLE_LLM_FALLBACK=true
JOB_AGENT_OLLAMA_MODEL=llama3.2:1b
```

If embeddings also feel heavy, keep transformer embeddings disabled. The app will use a lightweight built-in hash embedding instead.

## Run tests

```bash
python3 -m unittest discover -s tests -v
```

## Run the API

```bash
uvicorn job_agent.main:app --reload
```

Open the built-in UI in your browser:

```text
http://127.0.0.1:8000/
```

From there you can:
- upload a resume into MongoDB/GridFS
- connect to the WebSocket agent
- start an application run with a job URL and optional `profile_id`
- answer agent questions inline

The backend now stores profile-scoped resume chunks with metadata and uses a LangGraph loop for page read -> retrieval -> fill -> gap assessment -> human handoff.

If you still want to use a raw WebSocket client, send:

```json
{"type":"start","url":"https://company.workdayjobs.com/en-US/job"}
```

## Chrome extension mode

You can now run the filler inside the job page you already opened instead of launching a separate Playwright browser.

Load the unpacked extension from:

```text
/Users/goranshgattani/Desktop/Playground/chrome_extension
```

Setup:

1. Start the backend:

```bash
cd /Users/goranshgattani/Desktop/Playground
source .venv/bin/activate
python3 -m uvicorn job_agent.main:app --host 127.0.0.1 --port 8000 --log-level info
```

2. In Chrome, open `chrome://extensions`
3. Enable `Developer mode`
4. Click `Load unpacked`
5. Select `/Users/goranshgattani/Desktop/Playground/chrome_extension`

How it works:

- Open a job page in Chrome
- Open the extension popup
- Choose the candidate `Profile ID` you want the backend to use
- Press `Start`
- The extension scans visible fields in the current tab, asks the backend to classify and resolve values, then fills what it can
- If it hits unresolved fields, login gates, or document uploads, it pauses instead of spawning a new browser
- After you manually handle the blocker, press `Resume`

Current extension limitations:

- Resume and cover-letter uploads still pause for manual handling in extension mode
- Auto-submit is intentionally not performed from the extension popup
- The first version focuses on visible form fields and current-step `Apply` / `Next` actions

## Reuse a signed-in browser

Some job portals require Google sign-in or other account-backed flows. The agent can now avoid a fresh throwaway browser in two ways:

1. Recommended: launch a persistent Chrome profile

```env
JOB_AGENT_BROWSER_USE_PERSISTENT_CONTEXT=true
JOB_AGENT_BROWSER_CHANNEL=chrome
JOB_AGENT_BROWSER_USER_DATA_DIR=/Users/your-user/.job_agent_browser_profile
```

Sign into Google once in that browser profile, then reuse it on future runs.

2. Advanced: attach to a browser you launched yourself over CDP

Launch Chrome manually with remote debugging enabled, for example:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/Users/your-user/.job_agent_browser_profile
```

Then point the agent at that browser:

```env
JOB_AGENT_BROWSER_CDP_URL=http://127.0.0.1:9222
JOB_AGENT_BROWSER_CDP_NEW_WINDOW=true
```

In CDP mode the agent can request a real new Chrome window in that existing signed-in browser session instead of launching a separate browser process.

Do not point persistent mode at your normal Chrome profile while Chrome is already running. Use a dedicated agent profile directory instead.

## Suggested next integration steps

1. Seed a real profile document.
2. Verify one platform end-to-end with `JOB_AGENT_AUTO_SUBMIT=false`.
3. Turn on Mongo if you want persistent learned answers.
4. Only then enable the Ollama fallback with a small model.
