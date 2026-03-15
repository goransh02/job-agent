from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
except ImportError:
    FastAPI = None
    WebSocket = Any
    WebSocketDisconnect = Exception

from job_agent.agent.job_agent import JobAgent


def create_app():
    if FastAPI is None:
        raise RuntimeError(
            "FastAPI is not installed. Run `pip install -r job_agent/requirements.txt`."
        )

    app = FastAPI()
    agent = JobAgent()

    @app.websocket("/agent")
    async def agent_socket(ws: WebSocket):
        await ws.accept()

        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                break

            if data.get("type") != "start":
                await ws.send_json(
                    {
                        "type": "error",
                        "message": "Unsupported message type",
                    }
                )
                continue

            url = data.get("url")
            if not url:
                await ws.send_json(
                    {
                        "type": "error",
                        "message": "A job application URL is required",
                    }
                )
                continue

            try:
                result = await agent.run(url, websocket=ws)
            except Exception as exc:
                await ws.send_json({"type": "error", "message": str(exc)})
                continue

            await ws.send_json({"type": "complete", "result": result})

    return app


app = create_app() if FastAPI is not None else None
