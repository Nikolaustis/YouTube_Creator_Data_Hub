from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Envelope(BaseModel):
    ok: bool = True
    data: Any = None
    meta: dict[str, Any] = Field(default_factory=dict)
    api_version: Literal["v1"] = "v1"


class WorkspaceCreateRequest(BaseModel):
    name: str = ""
    template_id: str = "blank"


class WorkspaceActivateRequest(BaseModel):
    workspace_id: str


class CreatorListRequest(BaseModel):
    monitored_only: bool = False
    limit: int = Field(default=100, ge=1, le=5000)


class JobListRequest(BaseModel):
    limit: int = Field(default=30, ge=1, le=200)
