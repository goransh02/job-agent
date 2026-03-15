# Job Agent

This project is a job-application assistant built around FastAPI, Playwright, profile data, and optional local AI helpers.

## Current defaults

The app now starts in a safe, lightweight mode:

- Browser runs headless by default.
- Auto-submit is off by default.
- Mongo falls back to in-memory storage if it is unavailable.
- Transformer embeddings are off by default.
- Ollama fallback is off by default.

That means you can run tests and most app logic without immediately loading heavy local models.

## Install

```bash
python3 -m pip install -r job_agent/requirements.txt
playwright install chromium
```

## Configure

Copy `.env.example` to `.env` and set the values you need.

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

Open a WebSocket client and send:

```json
{"type":"start","url":"https://company.workdayjobs.com/en-US/job"}
```

## Suggested next integration steps

1. Seed a real profile document.
2. Verify one platform end-to-end with `JOB_AGENT_AUTO_SUBMIT=false`.
3. Turn on Mongo if you want persistent learned answers.
4. Only then enable the Ollama fallback with a small model.
