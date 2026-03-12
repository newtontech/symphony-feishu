"""Pydantic models for Symphony."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class IssueStatus(str, Enum):
    """Issue status from tracker."""

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    CANCELED = "canceled"


class IssuePriority(str, Enum):
    """Issue priority levels."""

    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class Issue(BaseModel):
    """Represents an issue from the tracker."""

    id: str
    identifier: str  # e.g., "SYM-123"
    title: str
    description: str | None = None
    status: IssueStatus
    priority: IssuePriority = IssuePriority.NONE
    labels: list[str] = Field(default_factory=list)
    assignee_id: str | None = None
    project_id: str | None = None
    created_at: str
    updated_at: str


class WorkflowConfig(BaseModel):
    """Configuration parsed from WORKFLOW.md YAML front matter."""

    name: str = "default"
    description: str | None = None
    tracker_filter: dict[str, Any] = Field(default_factory=dict)
    workspace_template: str | None = None
    max_concurrent: int = 1
    retry_limit: int = 3
    retry_delay_seconds: float = 60.0
    timeout_minutes: int = 60
    labels: list[str] = Field(default_factory=list)
    priority_filter: list[IssuePriority] = Field(default_factory=lambda: list(IssuePriority))


class Workflow(BaseModel):
    """Complete workflow definition."""

    config: WorkflowConfig
    prompt: str
    source_path: str | None = None


class WorkspaceState(str, Enum):
    """Workspace lifecycle states."""

    CREATING = "creating"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CLEANED = "cleaned"


class Workspace(BaseModel):
    """Represents an isolated workspace for agent execution."""

    id: UUID = Field(default_factory=uuid4)
    issue_id: str
    path: str
    state: WorkspaceState = WorkspaceState.CREATING
    created_at: str
    agent_pid: int | None = None
    error_message: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class AgentSession(BaseModel):
    """Represents an active agent session."""

    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    issue_id: str
    status: str = "starting"
    started_at: str
    completed_at: str | None = None
    tokens_used: int = 0
    error: str | None = None


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | list[Any] | None = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any = None
    error: dict[str, Any] | None = None


class JSONRPCError(BaseModel):
    """JSON-RPC error object."""

    code: int
    message: str
    data: Any | None = None


# Protocol message types
class ProtocolMessage(BaseModel):
    """Base protocol message."""

    type: str
    timestamp: str


class TaskUpdateMessage(ProtocolMessage):
    """Agent task update."""

    type: str = "task_update"
    task_id: str
    status: str
    progress: float | None = None
    message: str | None = None


class TokenUsageMessage(ProtocolMessage):
    """Token usage report."""

    type: str = "token_usage"
    session_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


class CompletionMessage(ProtocolMessage):
    """Agent completion notice."""

    type: str = "completion"
    session_id: str
    success: bool
    summary: str | None = None
    error: str | None = None


class OrchestratorState(str, Enum):
    """Orchestrator states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


class OrchestratorStatus(BaseModel):
    """Orchestrator status report."""

    state: OrchestratorState
    active_workspaces: int
    total_completed: int
    total_failed: int
    uptime_seconds: float
    current_workflow: str | None = None
    last_poll_time: str | None = None
    error: str | None = None


class Metrics(BaseModel):
    """System metrics."""

    total_issues_processed: int = 0
    total_issues_completed: int = 0
    total_issues_failed: int = 0
    total_tokens_used: int = 0
    total_workspaces_created: int = 0
    average_completion_time_seconds: float = 0.0
    last_updated: str | None = None
