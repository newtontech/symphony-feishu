"""Tests for orchestrator."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from symphony.config import Config
from symphony.models import (
    Issue,
    IssuePriority,
    IssueStatus,
    OrchestratorState,
    OrchestratorStatus,
    Workflow,
    WorkflowConfig,
)
from symphony.orchestrator import Orchestrator


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    config = MagicMock(spec=Config)
    config.poll_interval_seconds = 1.0
    config.tracker = MagicMock()
    config.workspace = MagicMock()
    config.agent = MagicMock()
    return config


@pytest.fixture
def mock_workflow():
    """Create mock workflow."""
    config = WorkflowConfig(
        name="test-workflow",
        max_concurrent=1,
        retry_limit=1,
        retry_delay_seconds=1.0,
    )
    return Workflow(
        config=config,
        prompt="Test prompt for {{ issue.identifier }}",
    )


@pytest.fixture
def mock_issue():
    """Create mock issue."""
    return Issue(
        id="issue-123",
        identifier="TEST-123",
        title="Test Issue",
        description="Test description",
        status=IssueStatus.TODO,
        priority=IssuePriority.MEDIUM,
        labels=["test"],
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def mock_tracker(mock_issue):
    """Create mock issue tracker."""
    tracker = AsyncMock()
    tracker.initialize = AsyncMock()
    tracker.close = AsyncMock()
    tracker.fetch_issues = AsyncMock(return_value=[mock_issue])
    tracker.update_status = AsyncMock(return_value=True)
    return tracker


@pytest.fixture
def mock_workspace_manager():
    """Create mock workspace manager."""
    from symphony.models import Workspace, WorkspaceState

    manager = AsyncMock()
    manager.initialize = AsyncMock()
    manager.create = AsyncMock(return_value=Workspace(
        id=uuid4(),
        issue_id="issue-123",
        path="/tmp/workspace",
        state=WorkspaceState.READY,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    manager.cleanup = AsyncMock()
    manager.list_all = AsyncMock(return_value=[])
    return manager


@pytest.fixture
def mock_agent_runner():
    """Create mock agent runner."""
    from symphony.models import AgentSession

    workspace_id = uuid4()
    runner = AsyncMock()
    runner.run = AsyncMock(return_value=AgentSession(
        id=uuid4(),
        workspace_id=workspace_id,
        issue_id="issue-123",
        status="completed",
        started_at=datetime.now(timezone.utc).isoformat(),
        tokens_used=1000,
    ))
    return runner


@pytest.mark.asyncio
async def test_orchestrator_initial_state(
    mock_config,
    mock_workflow,
    mock_tracker,
    mock_workspace_manager,
    mock_agent_runner,
):
    """Test orchestrator starts in stopped state."""
    orchestrator = Orchestrator(
        config=mock_config,
        workflow=mock_workflow,
        tracker=mock_tracker,
        workspace_manager=mock_workspace_manager,
        agent_runner=mock_agent_runner,
    )

    assert orchestrator.state == OrchestratorState.STOPPED


@pytest.mark.asyncio
async def test_orchestrator_start(
    mock_config,
    mock_workflow,
    mock_tracker,
    mock_workspace_manager,
    mock_agent_runner,
):
    """Test orchestrator starts successfully."""
    orchestrator = Orchestrator(
        config=mock_config,
        workflow=mock_workflow,
        tracker=mock_tracker,
        workspace_manager=mock_workspace_manager,
        agent_runner=mock_agent_runner,
    )

    # Start and immediately stop
    await orchestrator.start()

    assert orchestrator.state == OrchestratorState.RUNNING
    mock_tracker.initialize.assert_called_once()
    mock_workspace_manager.initialize.assert_called_once()

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_stop(
    mock_config,
    mock_workflow,
    mock_tracker,
    mock_workspace_manager,
    mock_agent_runner,
):
    """Test orchestrator stops gracefully."""
    orchestrator = Orchestrator(
        config=mock_config,
        workflow=mock_workflow,
        tracker=mock_tracker,
        workspace_manager=mock_workspace_manager,
        agent_runner=mock_agent_runner,
    )

    await orchestrator.start()
    await orchestrator.stop()

    assert orchestrator.state == OrchestratorState.STOPPED
    mock_tracker.close.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_pause_resume(
    mock_config,
    mock_workflow,
    mock_tracker,
    mock_workspace_manager,
    mock_agent_runner,
):
    """Test orchestrator pause and resume."""
    orchestrator = Orchestrator(
        config=mock_config,
        workflow=mock_workflow,
        tracker=mock_tracker,
        workspace_manager=mock_workspace_manager,
        agent_runner=mock_agent_runner,
    )

    await orchestrator.start()
    await orchestrator.pause()

    assert orchestrator.state == OrchestratorState.PAUSED

    await orchestrator.resume()

    assert orchestrator.state == OrchestratorState.RUNNING

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_get_status(
    mock_config,
    mock_workflow,
    mock_tracker,
    mock_workspace_manager,
    mock_agent_runner,
):
    """Test getting orchestrator status."""
    orchestrator = Orchestrator(
        config=mock_config,
        workflow=mock_workflow,
        tracker=mock_tracker,
        workspace_manager=mock_workspace_manager,
        agent_runner=mock_agent_runner,
    )

    await orchestrator.start()
    status = orchestrator.get_status()

    assert isinstance(status, OrchestratorStatus)
    assert status.state == OrchestratorState.RUNNING
    assert status.current_workflow == "test-workflow"

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_processes_issue(
    mock_config,
    mock_workflow,
    mock_tracker,
    mock_workspace_manager,
    mock_agent_runner,
    mock_issue,
):
    """Test orchestrator processes an issue."""
    orchestrator = Orchestrator(
        config=mock_config,
        workflow=mock_workflow,
        tracker=mock_tracker,
        workspace_manager=mock_workspace_manager,
        agent_runner=mock_agent_runner,
    )

    await orchestrator.start()

    # Give it a moment to process
    await asyncio.sleep(0.5)

    # Verify issue was fetched
    mock_tracker.fetch_issues.assert_called()

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_metrics(
    mock_config,
    mock_workflow,
    mock_tracker,
    mock_workspace_manager,
    mock_agent_runner,
):
    """Test orchestrator tracks metrics."""
    orchestrator = Orchestrator(
        config=mock_config,
        workflow=mock_workflow,
        tracker=mock_tracker,
        workspace_manager=mock_workspace_manager,
        agent_runner=mock_agent_runner,
    )

    metrics = orchestrator.metrics

    assert metrics.total_issues_processed == 0
    assert metrics.total_issues_completed == 0
    assert metrics.total_issues_failed == 0


@pytest.mark.asyncio
async def test_orchestrator_capacity_limit(
    mock_config,
    mock_workflow,
    mock_tracker,
    mock_workspace_manager,
    mock_agent_runner,
    mock_issue,
):
    """Test orchestrator respects max_concurrent limit."""
    # Set max_concurrent to 1
    mock_workflow.config.max_concurrent = 1

    orchestrator = Orchestrator(
        config=mock_config,
        workflow=mock_workflow,
        tracker=mock_tracker,
        workspace_manager=mock_workspace_manager,
        agent_runner=mock_agent_runner,
    )

    await orchestrator.start()
    await asyncio.sleep(0.5)

    # With max_concurrent=1, should only process one at a time
    status = orchestrator.get_status()
    assert status.active_workspaces <= 1

    await orchestrator.stop()
