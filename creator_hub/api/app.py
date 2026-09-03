from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from creator_hub import __version__
from creator_hub.config import DEFAULT_DB
from creator_hub.jobs import JobEngine
from creator_hub.service import CreatorHub

from .models import (
    CreatorListRequest,
    Envelope,
    JobListRequest,
    WorkspaceActivateRequest,
    WorkspaceCreateRequest,
)

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _envelope(data: Any = None, **meta: Any) -> Envelope:
    return Envelope(data=data, meta=meta)


def create_app(db_path: str | Path = DEFAULT_DB) -> FastAPI:
    db = str(db_path)
    app = FastAPI(
        title="YouTube Creator Intelligence Hub API",
        version=__version__,
        description=(
            "Typed API for new Creator Intelligence integrations. The historical Dashboard "
            "HTTP server remains a compatibility layer during the V4 migration."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.db_path = db
    app.state.hub = CreatorHub(db)
    app.state.jobs = JobEngine(db)

    def hub() -> CreatorHub:
        return app.state.hub

    def jobs() -> JobEngine:
        return app.state.jobs

    def local_write(request: Request) -> None:
        host = (request.client.host if request.client else "") or ""
        if host not in LOOPBACK_HOSTS:
            raise HTTPException(
                status_code=403,
                detail="write endpoints are loopback-only by default",
            )

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc), "api_version": "v1"})

    @app.get("/api/v1/health", response_model=Envelope)
    def health(current: CreatorHub = Depends(hub), engine: JobEngine = Depends(jobs)) -> Envelope:
        return _envelope(
            {
                "version": __version__,
                "db": str(Path(current.db_path).resolve()),
                "db_exists": Path(current.db_path).exists(),
                "workspace": current.workspace.active(),
                "job_durability": engine.durability_health(),
            }
        )

    @app.get("/api/v1/workspaces", response_model=Envelope)
    def workspaces(current: CreatorHub = Depends(hub)) -> Envelope:
        return _envelope(
            {
                "workspaces": current.workspace.list(),
                "active": current.workspace.active(),
                "templates": current.workspace.templates(),
            }
        )

    @app.get("/api/v1/workspaces/{workspace_id}", response_model=Envelope)
    def workspace_context(workspace_id: str, current: CreatorHub = Depends(hub)) -> Envelope:
        context = current.workspace.context(workspace_id)
        if not context.get("workspace"):
            raise HTTPException(status_code=404, detail="workspace not found")
        return _envelope(context)

    @app.post("/api/v1/workspaces", response_model=Envelope, dependencies=[Depends(local_write)])
    def create_workspace(body: WorkspaceCreateRequest, current: CreatorHub = Depends(hub)) -> Envelope:
        if body.template_id == "blank":
            workspace = current.workspace.create_blank(body.name)
        else:
            workspace = current.workspace.install_template(body.template_id, name=body.name)
        return _envelope(workspace)

    @app.post("/api/v1/workspaces/activate", response_model=Envelope, dependencies=[Depends(local_write)])
    def activate_workspace(body: WorkspaceActivateRequest, current: CreatorHub = Depends(hub)) -> Envelope:
        workspace = current.workspace.set_active(body.workspace_id)
        current.brand_cfg = current.workspace.classifier_config(current.legacy_brand_cfg)
        return _envelope(workspace)

    @app.post("/api/v1/creators/query", response_model=Envelope)
    def creators(body: CreatorListRequest, current: CreatorHub = Depends(hub)) -> Envelope:
        rows = current.list_creators(monitored_only=body.monitored_only, limit=body.limit)
        return _envelope({"rows": rows, "count": len(rows)})

    @app.post("/api/v1/jobs/query", response_model=Envelope)
    def job_list(body: JobListRequest, engine: JobEngine = Depends(jobs)) -> Envelope:
        return _envelope(
            {
                "rows": engine.list(body.limit),
                "durability": engine.durability_health(),
            }
        )

    return app
