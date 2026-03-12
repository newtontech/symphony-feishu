"""HTTP API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from symphony.models import OrchestratorState

router = APIRouter()


class StatusResponse(BaseModel):
    """Status response model."""

    state: str
    active_workspaces: int
    total_completed: int
    total_failed: int
    uptime_seconds: float
    workflow: str | None = None


class ActionRequest(BaseModel):
    """Action request model."""

    action: str


class ValidateRequest(BaseModel):
    """Validate workflow request."""

    workflow_path: str


class ValidateResponse(BaseModel):
    """Validate workflow response."""

    valid: bool
    errors: list[str] = []


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request) -> StatusResponse:
    """Get orchestrator status."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    status = orchestrator.get_status()
    return StatusResponse(
        state=status.state.value,
        active_workspaces=status.active_workspaces,
        total_completed=status.total_completed,
        total_failed=status.total_failed,
        uptime_seconds=status.uptime_seconds,
        workflow=status.current_workflow,
    )


@router.post("/action")
async def perform_action(request: Request, action: ActionRequest) -> dict[str, Any]:
    """Perform an orchestrator action.

    Actions:
    - start: Start the orchestrator
    - stop: Stop the orchestrator
    - pause: Pause the orchestrator
    - resume: Resume the orchestrator
    """
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    actions = {
        "start": orchestrator.start,
        "stop": orchestrator.stop,
        "pause": orchestrator.pause,
        "resume": orchestrator.resume,
    }

    handler = actions.get(action.action)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    await handler()
    return {"success": True, "action": action.action, "state": orchestrator.state.value}


@router.get("/metrics")
async def get_metrics(request: Request) -> dict[str, Any]:
    """Get orchestrator metrics."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    return orchestrator.metrics.model_dump()


@router.get("/workspaces")
async def list_workspaces(request: Request) -> list[dict[str, Any]]:
    """List active workspaces."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    # Access workspace manager through orchestrator
    workspaces = await orchestrator.workspace_manager.list_all()
    return [ws.model_dump() for ws in workspaces]


@router.post("/validate", response_model=ValidateResponse)
async def validate_workflow(req: ValidateRequest) -> ValidateResponse:
    """Validate a workflow file."""
    from pathlib import Path

    from symphony.workflow import validate_workflow

    errors = validate_workflow(Path(req.workflow_path))
    return ValidateResponse(
        valid=len(errors) == 0,
        errors=errors,
    )


@router.get("/workflow")
async def get_workflow(request: Request) -> dict[str, Any]:
    """Get current workflow configuration."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    return {
        "name": orchestrator.workflow.config.name,
        "description": orchestrator.workflow.config.description,
        "max_concurrent": orchestrator.workflow.config.max_concurrent,
        "retry_limit": orchestrator.workflow.config.retry_limit,
        "timeout_minutes": orchestrator.workflow.config.timeout_minutes,
        "labels": orchestrator.workflow.config.labels,
    }


# Dashboard HTML (simple)
@router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, Any]:
    """Get dashboard data."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        return {"error": "Orchestrator not initialized"}

    status = orchestrator.get_status()
    metrics = orchestrator.metrics

    return {
        "status": status.model_dump(),
        "metrics": metrics.model_dump(),
        "config": {
            "workflow": orchestrator.workflow.config.name,
            "poll_interval": request.app.state.config.poll_interval_seconds,
        },
    }
