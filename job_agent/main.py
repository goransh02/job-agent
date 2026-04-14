from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:
    FastAPI = None
    File = None
    HTTPException = RuntimeError
    UploadFile = Any
    WebSocket = Any
    WebSocketDisconnect = Exception
    FileResponse = Any
    StaticFiles = Any
    StreamingResponse = Any

from job_agent.agent.job_agent import JobAgent
from job_agent.logging_utils import trace
from job_agent.services.extension_service import build_extension_fill_plan
from job_agent.services.resume_service import (
    ResumeStorageError,
    get_resume_metadata,
    get_resume_upload_path,
    store_resume,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    force=True,
)

logger = logging.getLogger(__name__)
UI_DIR = Path(__file__).resolve().parent / "ui"


def create_app():
    if FastAPI is None:
        raise RuntimeError(
            "FastAPI is not installed. Run `pip install -r job_agent/requirements.txt`."
        )

    app = FastAPI()
    agent = JobAgent()
    app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    @app.get("/")
    async def ui_home():
        return FileResponse(UI_DIR / "index.html")

    @app.post("/api/profile/resume")
    async def upload_resume(profile_id: str | None = None, file: UploadFile = File(...)):
        if file is None:
            raise HTTPException(status_code=400, detail="Resume file is required")

        content = await file.read()
        try:
            metadata = store_resume(
                content,
                filename=file.filename,
                content_type=file.content_type,
                attach_to_profile=True,
                profile_id=profile_id,
            )
        except ResumeStorageError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return {
            "message": "Resume stored successfully",
            **metadata,
        }

    @app.get("/api/profile/resume")
    async def get_resume(profile_id: str | None = None):
        metadata = get_resume_metadata(profile_id=profile_id)
        if metadata is None:
            raise HTTPException(status_code=404, detail="No resume is stored in the profile")
        return metadata

    @app.post("/api/extension/resolve")
    async def resolve_extension_fields(payload: dict[str, Any]):
        fields = payload.get("fields")
        if not isinstance(fields, list):
            raise HTTPException(status_code=400, detail="`fields` must be a list")

        url = str(payload.get("url") or "").strip()
        profile_id = payload.get("profile_id")
        return build_extension_fill_plan(url, fields, profile_id=profile_id)

    @app.get("/api/profile/resume/download")
    async def download_resume(profile_id: str | None = None):
        metadata = get_resume_metadata(profile_id=profile_id)
        if metadata is None:
            raise HTTPException(status_code=404, detail="No resume is stored in the profile")

        try:
            upload_path = get_resume_upload_path(profile_id=profile_id)
        except ResumeStorageError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        if upload_path is None:
            raise HTTPException(status_code=404, detail="No resume file is available")

        path = Path(upload_path)
        media_type = metadata.get("resume_content_type") or "application/octet-stream"
        filename = metadata.get("resume_filename") or path.name
        return StreamingResponse(
            iter([path.read_bytes()]),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.websocket("/agent")
    async def agent_socket(ws: WebSocket):
        trace(logger, "WebSocket connection request received for /agent")
        await ws.accept()
        trace(logger, "WebSocket connection accepted")
        await ws.send_json(
            {
                "type": "connected",
                "message": "WebSocket connected. Send a JSON payload with type=start and a url.",
            }
        )

        while True:
            try:
                trace(logger, "Waiting for websocket payload")
                frame = await ws.receive()
            except WebSocketDisconnect:
                trace(logger, "WebSocket client disconnected")
                break
            except Exception:
                logger.exception("Failed to receive websocket payload")
                await ws.send_json({"type": "error", "message": "Invalid websocket payload"})
                continue

            frame_type = frame.get("type")
            if frame_type == "websocket.disconnect":
                trace(logger, "WebSocket disconnect frame received")
                break

            trace(
                logger,
                "Raw websocket frame received: type=%s has_text=%s has_bytes=%s",
                frame_type,
                frame.get("text") is not None,
                frame.get("bytes") is not None,
            )

            raw_payload = frame.get("text")
            if raw_payload is None and frame.get("bytes") is not None:
                try:
                    raw_payload = frame["bytes"].decode("utf-8")
                except Exception:
                    logger.exception("Failed to decode websocket bytes payload")
                    await ws.send_json(
                        {
                            "type": "error",
                            "message": "WebSocket payload bytes are not valid UTF-8 JSON",
                        }
                    )
                    continue

            if raw_payload is None:
                logger.warning("Received websocket frame without text payload")
                await ws.send_json(
                    {
                        "type": "error",
                        "message": "Expected a text JSON payload",
                    }
                )
                continue

            try:
                data = json.loads(raw_payload)
            except json.JSONDecodeError:
                logger.exception("Failed to decode websocket JSON payload: %s", raw_payload)
                await ws.send_json(
                    {
                        "type": "error",
                        "message": "Payload must be valid JSON text",
                    }
                )
                continue

            trace(logger, "Received websocket payload: %s", data)

            message_type = data.get("type")

            if message_type not in {"start", "continue"}:
                logger.warning("Unsupported websocket message type: %s", data.get("type"))
                await ws.send_json(
                    {
                        "type": "error",
                        "message": "Unsupported message type",
                    }
                )
                continue

            try:
                if message_type == "start":
                    url = data.get("url")
                    profile_id = data.get("profile_id")
                    if not url:
                        logger.warning("Start message missing URL")
                        await ws.send_json(
                            {
                                "type": "error",
                                "message": "A job application URL is required",
                            }
                        )
                        continue

                    trace(logger, "Starting agent run for URL: %s", url)
                    result = await agent.run(url, websocket=ws, profile_id=profile_id)
                    trace(logger, "Agent run completed successfully: %s", result)
                else:
                    trace(logger, "Continuing active agent run")
                    result = await agent.continue_run(
                        websocket=ws,
                        application_id=data.get("application_id"),
                        profile_id=data.get("profile_id"),
                    )
                    trace(logger, "Agent continue completed successfully: %s", result)
            except Exception as exc:
                logger.exception("Agent websocket command failed: %s", message_type)
                await ws.send_json({"type": "error", "message": str(exc)})
                continue

            if result.get("can_continue") and not result.get("submitted"):
                await ws.send_json(
                    {
                        "type": "paused",
                        "message": "Run paused for user intervention. Keep the browser open and press Play/Resume when ready.",
                        "result": result,
                    }
                )
                trace(logger, "Paused payload sent to websocket client")
            else:
                await ws.send_json({"type": "complete", "result": result})
                trace(logger, "Completion payload sent to websocket client")

    return app


app = create_app() if FastAPI is not None else None
