from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.runtime_session import create_runtime_session, normalize_jira_id

HOST = os.getenv("AEF_HOST", "127.0.0.1")
PORT = int(os.getenv("AEF_PORT", "8787"))
API_TOKEN = os.getenv("AEF_API_TOKEN", "")
PROJECT_ID = os.getenv("AEF_PROJECT_ID", "")
RUNTIME_VERSION = os.getenv("AEF_RUNTIME_VERSION", "2026.07.28")

app = FastAPI(title="AI Engineering Framework Backend")


def _is_authorized(authorization: str | None) -> bool:
    if not API_TOKEN:
        return True
    return authorization == f"Bearer {API_TOKEN}"


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not _is_authorized(request.headers.get("authorization")):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "ai-engineering-framework-backend",
        "version": RUNTIME_VERSION,
    }


@app.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    return {
        "capabilities": [
            "DtoC",
            "jira-runtime-session",
            "project-aware-planning",
            "protected-thin-client",
        ]
    }


@app.post("/runtime/session")
async def runtime_session(request: Request, authorization: str | None = Header(default=None)):
    try:
        body = await request.json()
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": "invalid_request", "message": str(exc)})

    jira_id = normalize_jira_id(body.get("jiraId"))
    if not jira_id:
        return JSONResponse(status_code=400, content={"error": "missing_jira_id", "message": "jiraId is required"})

    try:
        payload = await create_runtime_session(body=body, runtime_version=RUNTIME_VERSION, project_id=PROJECT_ID)
        return JSONResponse(status_code=200, content=payload)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": "invalid_request", "message": str(exc)})
