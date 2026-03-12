"""Tests for agent runner."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from symphony.config import AgentConfig
from symphony.models import AgentSession, Issue, IssuePriority, IssueStatus, Workflow, WorkflowConfig, Workspace, WorkspaceState
from symphony.agent_runner import AgentError, AgentRunner


@pytest.fixture
def agent_config():
    """Create agent configuration."""
    return AgentConfig(
        executable="/usr/bin/agent",
        timeout_seconds=60,
    )


@pytest.fixture
def mock_workspace():
    """Create a mock workspace."""
    return Workspace(
        id=uuid4(),
        issue_id="issue-123",
        path="/tmp/workspace",
        state=WorkspaceState.READY,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def mock_issue():
    """Create a mock issue."""
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
def mock_workflow():
    """Create a mock workflow."""
    config = WorkflowConfig(
        name="test-workflow",
        max_concurrent=1,
        retry_limit=1,
        retry_delay_seconds=1.0,
    )
    return Workflow(
        config=config,
        prompt="Work on {{ issue.identifier }}: {{ issue.title }}",
    )


def test_agent_runner_init(agent_config):
    """Test agent runner initialization."""
    runner = AgentRunner(agent_config)

    assert runner.config == agent_config
    assert runner._sessions == {}
    assert runner._processes == {}


@pytest.mark.asyncio
async def test_get_session(agent_config):
    """Test getting a session by ID."""
    runner = AgentRunner(agent_config)

    session_id = str(uuid4())
    session = AgentSession(
        id=uuid4(),
        workspace_id=uuid4(),
        issue_id="issue-123",
        status="completed",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    runner._sessions[session_id] = session

    result = await runner.get_session(session_id)
    assert result == session

    # Test non-existent session
    result = await runner.get_session("non-existent")
    assert result is None


@pytest.mark.asyncio
async def test_list_sessions(agent_config):
    """Test listing all sessions."""
    runner = AgentRunner(agent_config)

    session1 = AgentSession(
        id=uuid4(),
        workspace_id=uuid4(),
        issue_id="issue-1",
        status="completed",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    session2 = AgentSession(
        id=uuid4(),
        workspace_id=uuid4(),
        issue_id="issue-2",
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    runner._sessions["session-1"] = session1
    runner._sessions["session-2"] = session2

    sessions = await runner.list_sessions()

    assert len(sessions) == 2
    assert session1 in sessions
    assert session2 in sessions


@pytest.mark.asyncio
async def test_cancel_session(agent_config):
    """Test cancelling a running session."""
    runner = AgentRunner(agent_config)

    session_id = "session-123"
    session = AgentSession(
        id=uuid4(),
        workspace_id=uuid4(),
        issue_id="issue-123",
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    runner._sessions[session_id] = session

    # Create a mock process
    mock_process = MagicMock()
    mock_process.returncode = None
    mock_process.terminate = MagicMock()
    mock_process.wait = AsyncMock()
    runner._processes[session_id] = mock_process

    result = await runner.cancel_session(session_id)

    assert result is True
    assert session.status == "cancelled"
    assert session.error == "Session cancelled by user"
    mock_process.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_nonexistent_session(agent_config):
    """Test cancelling a non-existent session."""
    runner = AgentRunner(agent_config)

    result = await runner.cancel_session("non-existent")
    assert result is False


def test_render_prompt(agent_config, mock_workflow, mock_issue, mock_workspace):
    """Test prompt rendering."""
    runner = AgentRunner(agent_config)

    prompt = runner._render_prompt(mock_workflow, mock_issue, mock_workspace)

    assert "TEST-123" in prompt
    assert "Test Issue" in prompt


def test_setup_protocol_handlers(agent_config):
    """Test setting up protocol handlers."""
    runner = AgentRunner(agent_config)

    protocol = MagicMock()
    protocol.on_request = MagicMock()

    session = AgentSession(
        id=uuid4(),
        workspace_id=uuid4(),
        issue_id="issue-123",
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    runner._setup_protocol_handlers(protocol, session)

    # Should register handlers for task/update, log/message, tokens/report
    assert protocol.on_request.call_count == 3
    registered_methods = [call[0][0] for call in protocol.on_request.call_args_list]
    assert "task/update" in registered_methods
    assert "log/message" in registered_methods
    assert "tokens/report" in registered_methods


@pytest.mark.asyncio
async def test_run_agent_success(agent_config, mock_workspace, mock_issue, mock_workflow):
    """Test successful agent run."""
    runner = AgentRunner(agent_config)

    with patch.object(runner, '_start_agent') as mock_start:
        # Mock process
        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.wait = AsyncMock()
        mock_process.returncode = 0
        mock_process.terminate = MagicMock()

        mock_start.return_value = mock_process

        # Mock ProtocolHandler
        with patch('symphony.agent_runner.ProtocolHandler') as mock_protocol_class:
            mock_protocol = MagicMock()
            mock_protocol.start = AsyncMock()
            mock_protocol.stop = AsyncMock()
            mock_protocol.send_request = AsyncMock(return_value={})
            mock_protocol_class.return_value = mock_protocol

            session = await runner.run(mock_workspace, mock_issue, mock_workflow)

            assert session.status == "completed"
            assert session.error is None


@pytest.mark.asyncio
async def test_run_agent_timeout(agent_config, mock_workspace, mock_issue, mock_workflow):
    """Test agent run with timeout."""
    # Set a very short timeout
    agent_config.timeout_seconds = 0.1

    runner = AgentRunner(agent_config)

    with patch.object(runner, '_start_agent') as mock_start:
        # Mock process that doesn't finish
        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.returncode = None
        mock_process.terminate = MagicMock()

        mock_start.return_value = mock_process

        # Mock ProtocolHandler
        with patch('symphony.agent_runner.ProtocolHandler') as mock_protocol_class:
            mock_protocol = MagicMock()
            mock_protocol.start = AsyncMock()
            mock_protocol.stop = AsyncMock()
            mock_protocol.send_request = AsyncMock(return_value={})
            mock_protocol_class.return_value = mock_protocol

            session = await runner.run(mock_workspace, mock_issue, mock_workflow)

            assert session.status == "timeout"
            assert "timed out" in session.error.lower()