"""Tests for Linear issue tracker client."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from symphony.config import TrackerConfig
from symphony.models import Issue, IssuePriority, IssueStatus
from symphony.tracker.base import IssueTracker
from symphony.tracker.linear import LinearClient, PRIORITY_MAPPING


@pytest.fixture
def tracker_config():
    """Create tracker configuration."""
    return TrackerConfig(
        linear_api_key="test-api-key",
        linear_team_id="test-team-id",
        linear_project_id=None,
        linear_api_url="https://api.linear.app/graphql",
    )


@pytest.fixture
def mock_linear_response():
    """Create mock Linear GraphQL response."""
    return {
        "data": {
            "issues": {
                "nodes": [
                    {
                        "id": "issue-1",
                        "identifier": "TEST-1",
                        "title": "Test Issue 1",
                        "description": "Description 1",
                        "state": {"name": "Todo", "type": "unstarted"},
                        "priority": 3,
                        "labels": {"nodes": [{"name": "symphony"}]},
                        "assignee": {"id": "user-1"},
                        "project": {"id": "project-1"},
                        "createdAt": "2024-01-01T00:00:00Z",
                        "updatedAt": "2024-01-01T00:00:00Z",
                    },
                    {
                        "id": "issue-2",
                        "identifier": "TEST-2",
                        "title": "Test Issue 2",
                        "description": "Description 2",
                        "state": {"name": "In Progress", "type": "started"},
                        "priority": 2,
                        "labels": {"nodes": [{"name": "symphony"}, {"name": "bug"}]},
                        "assignee": None,
                        "project": None,
                        "createdAt": "2024-01-02T00:00:00Z",
                        "updatedAt": "2024-01-02T00:00:00Z",
                    },
                ],
                "pageInfo": {
                    "hasNextPage": False,
                    "endCursor": None,
                },
            }
        }
    }


@pytest.mark.asyncio
async def test_linear_client_initialize(tracker_config):
    """Test Linear client initialization."""
    client = LinearClient(tracker_config)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"workflowStates": {"nodes": []}}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await client.initialize()
        # Should not raise any errors


@pytest.mark.asyncio
async def test_linear_client_close(tracker_config):
    """Test Linear client close."""
    client = LinearClient(tracker_config)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"workflowStates": {"nodes": []}}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await client.initialize()
        await client.close()
        # Should not raise any errors


@pytest.mark.asyncio
async def test_linear_client_fetch_issues(tracker_config, mock_linear_response):
    """Test fetching issues from Linear."""
    client = LinearClient(tracker_config)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Mock workflow states response
        mock_state_response = MagicMock()
        mock_state_response.json.return_value = {
            "data": {"workflowStates": {"nodes": []}}
        }
        mock_state_response.raise_for_status = MagicMock()

        # Mock issues response
        mock_issues_response = MagicMock()
        mock_issues_response.json.return_value = mock_linear_response
        mock_issues_response.raise_for_status = MagicMock()

        mock_client.post.side_effect = [mock_state_response, mock_issues_response]

        await client.initialize()
        issues = await client.fetch_issues()

        assert len(issues) == 2
        assert issues[0].identifier == "TEST-1"
        assert issues[0].title == "Test Issue 1"
        assert issues[0].status == IssueStatus.TODO
        assert issues[0].priority == IssuePriority.MEDIUM
        assert issues[1].identifier == "TEST-2"
        assert issues[1].status == IssueStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_linear_client_update_status(tracker_config):
    """Test updating issue status in Linear."""
    client = LinearClient(tracker_config)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Mock workflow states response with state ids
        mock_state_response = MagicMock()
        mock_state_response.json.return_value = {
            "data": {
                "workflowStates": {
                    "nodes": [
                        {"id": "state-done", "name": "Done", "type": "completed"},
                    ]
                }
            }
        }
        mock_state_response.raise_for_status = MagicMock()

        # Mock update response
        mock_update_response = MagicMock()
        mock_update_response.json.return_value = {
            "data": {"issueUpdate": {"success": True}}
        }
        mock_update_response.raise_for_status = MagicMock()

        mock_client.post.side_effect = [mock_state_response, mock_update_response]

        await client.initialize()
        result = await client.update_status("issue-1", IssueStatus.DONE)

        assert result is True


@pytest.mark.asyncio
async def test_linear_client_priority_mapping(tracker_config):
    """Test Linear priority to internal priority mapping."""
    # Linear priorities: 0=none, 1=urgent, 2=high, 3=medium, 4=low
    assert PRIORITY_MAPPING[0] == IssuePriority.NONE
    assert PRIORITY_MAPPING[1] == IssuePriority.URGENT
    assert PRIORITY_MAPPING[2] == IssuePriority.HIGH
    assert PRIORITY_MAPPING[3] == IssuePriority.MEDIUM
    assert PRIORITY_MAPPING[4] == IssuePriority.LOW


@pytest.mark.asyncio
async def test_linear_client_parse_issue(tracker_config):
    """Test parsing Linear issue data."""
    client = LinearClient(tracker_config)

    issue_data = {
        "id": "test-id",
        "identifier": "TEST-123",
        "title": "Test Title",
        "description": "Test description",
        "state": {"name": "Todo", "type": "unstarted"},
        "priority": 1,
        "labels": {"nodes": [{"name": "bug"}, {"name": "urgent"}]},
        "assignee": {"id": "user-123"},
        "project": {"id": "proj-456"},
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
    }

    issue = client._parse_issue(issue_data)

    assert issue.id == "test-id"
    assert issue.identifier == "TEST-123"
    assert issue.title == "Test Title"
    assert issue.description == "Test description"
    assert issue.status == IssueStatus.TODO
    assert issue.priority == IssuePriority.URGENT
    assert "bug" in issue.labels
    assert "urgent" in issue.labels
    assert issue.assignee_id == "user-123"
    assert issue.project_id == "proj-456"