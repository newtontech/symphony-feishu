"""Tests for Feishu Task v2 tracker client."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from symphony.models import Issue, IssuePriority, IssueStatus
from symphony.tracker.feishu import (
    FEISHU_TO_PRIORITY,
    FEISHU_TO_STATUS,
    STATUS_TO_FEISHU,
    FeishuClient,
    _extract_plain_text,
)


def _make_config(**overrides):
    """Create a mock TrackerConfig with Feishu fields."""
    cfg = MagicMock()
    cfg.feishu_app_id = overrides.get("app_id", "cli_test_app_id")
    cfg.feishu_app_secret = overrides.get("app_secret", "test_app_secret")
    cfg.feishu_tasklist_id = overrides.get("tasklist_id", "tl_guid_123")
    cfg.feishu_base_url = overrides.get("base_url", "https://open.feishu.cn")
    return cfg


def _auth_response():
    return {"code": 0, "msg": "ok", "tenant_access_token": "t-mock-token", "expire": 7200}


def _task_list_response(items=None):
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "items": items or [],
            "has_more": False,
            "page_token": "",
        },
    }


def _sample_task(guid="guid-abc12345", status="not_started", priority=3):
    return {
        "task_guid": guid,
        "summary": "Implement login",
        "description": {
            "rich_text": [{"type": "text", "text": "Need to implement OAuth2"}]
        },
        "status": status,
        "priority": priority,
        "created_at": "1709000000",
        "updated_at": "1709000100",
        "tags": ["backend"],
    }


def _single_task_response(task=None):
    return {
        "code": 0,
        "msg": "success",
        "data": {"task": task or _sample_task()},
    }


@pytest.fixture
def config():
    return _make_config()


@pytest.fixture
def client(config):
    return FeishuClient(config)


# ---------------------------------------------------------------------------
# initialize / close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_success(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http
        mock_resp = MagicMock()
        mock_resp.json.return_value = _auth_response()
        mock_resp.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_resp

        await client.initialize()
        assert client._token == "t-mock-token"


@pytest.mark.asyncio
async def test_initialize_missing_app_id():
    cfg = _make_config(app_id=None)
    c = FeishuClient(cfg)
    with pytest.raises(ValueError, match="FEISHU_APP_ID"):
        await c.initialize()


@pytest.mark.asyncio
async def test_initialize_missing_app_secret():
    cfg = _make_config(app_secret=None)
    c = FeishuClient(cfg)
    with pytest.raises(ValueError, match="FEISHU_APP_SECRET"):
        await c.initialize()


@pytest.mark.asyncio
async def test_close(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http
        mock_resp = MagicMock()
        mock_resp.json.return_value = _auth_response()
        mock_resp.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_resp

        await client.initialize()
        await client.close()
        assert client._client is None


# ---------------------------------------------------------------------------
# fetch_issues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_issues_success(client):
    task1 = _sample_task(guid="g1", status="not_started", priority=3)
    task2 = _sample_task(guid="g2", status="in_progress", priority=1)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        fetch_resp = MagicMock()
        fetch_resp.json.return_value = _task_list_response([task1, task2])
        fetch_resp.raise_for_status = MagicMock()
        fetch_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = fetch_resp

        await client.initialize()
        issues = await client.fetch_issues()

    assert len(issues) == 2
    assert issues[0].id == "g1"
    assert issues[0].title == "Implement login"
    assert issues[0].status == IssueStatus.TODO
    assert issues[0].priority == IssuePriority.HIGH
    assert issues[1].status == IssueStatus.IN_PROGRESS
    assert issues[1].priority == IssuePriority.LOW


@pytest.mark.asyncio
async def test_fetch_issues_empty(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        fetch_resp = MagicMock()
        fetch_resp.json.return_value = _task_list_response([])
        fetch_resp.raise_for_status = MagicMock()
        fetch_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = fetch_resp

        await client.initialize()
        issues = await client.fetch_issues()

    assert issues == []


@pytest.mark.asyncio
async def test_fetch_issues_with_filter(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        fetch_resp = MagicMock()
        fetch_resp.json.return_value = _task_list_response([])
        fetch_resp.raise_for_status = MagicMock()
        fetch_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = fetch_resp

        await client.initialize()
        await client.fetch_issues(filter={"status": "in_progress"})

        call_kwargs = mock_http.request.call_args
        assert call_kwargs is not None


# ---------------------------------------------------------------------------
# get_issue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_issue_success(client):
    task = _sample_task(guid="guid-xyz", status="in_progress", priority=2)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        get_resp = MagicMock()
        get_resp.json.return_value = _single_task_response(task)
        get_resp.raise_for_status = MagicMock()
        get_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = get_resp

        await client.initialize()
        issue = await client.get_issue("guid-xyz")

    assert issue is not None
    assert issue.id == "guid-xyz"
    assert issue.status == IssueStatus.IN_PROGRESS
    assert issue.priority == IssuePriority.MEDIUM


@pytest.mark.asyncio
async def test_get_issue_not_found(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        error_resp = MagicMock()
        error_resp.json.return_value = {"code": 0, "data": {}}
        error_resp.raise_for_status = MagicMock()
        error_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = error_resp

        await client.initialize()
        issue = await client.get_issue("nonexistent")

    assert issue is None


@pytest.mark.asyncio
async def test_get_issue_api_error(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        error_resp = MagicMock()
        error_resp.json.return_value = {"code": 1001, "msg": "not found", "data": {}}
        error_resp.raise_for_status = MagicMock()
        error_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = error_resp

        await client.initialize()
        issue = await client.get_issue("bad-id")

    assert issue is None


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_status_todo(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        update_resp = MagicMock()
        update_resp.json.return_value = {"code": 0, "data": {}}
        update_resp.raise_for_status = MagicMock()
        update_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = update_resp

        await client.initialize()
        result = await client.update_status("guid-1", IssueStatus.TODO)

    assert result is True


@pytest.mark.asyncio
async def test_update_status_in_progress(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        update_resp = MagicMock()
        update_resp.json.return_value = {"code": 0, "data": {}}
        update_resp.raise_for_status = MagicMock()
        update_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = update_resp

        await client.initialize()
        result = await client.update_status("guid-1", IssueStatus.IN_PROGRESS)

    assert result is True


@pytest.mark.asyncio
async def test_update_status_done(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        update_resp = MagicMock()
        update_resp.json.return_value = {"code": 0, "data": {}}
        update_resp.raise_for_status = MagicMock()
        update_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = update_resp

        await client.initialize()
        result = await client.update_status("guid-1", IssueStatus.DONE)

    assert result is True


# ---------------------------------------------------------------------------
# add_comment / add_labels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_comment_success(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        comment_resp = MagicMock()
        comment_resp.json.return_value = {"code": 0, "data": {}}
        comment_resp.raise_for_status = MagicMock()
        comment_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = comment_resp

        await client.initialize()
        result = await client.add_comment("guid-1", "PR created: #42")

    assert result is True


@pytest.mark.asyncio
async def test_add_labels_not_supported(client):
    result = await client.add_labels("guid-1", ["bug"])
    assert result is False


# ---------------------------------------------------------------------------
# mappings
# ---------------------------------------------------------------------------


def test_feishu_status_mapping():
    assert FEISHU_TO_STATUS["not_started"] == IssueStatus.TODO
    assert FEISHU_TO_STATUS["in_progress"] == IssueStatus.IN_PROGRESS
    assert FEISHU_TO_STATUS["completed"] == IssueStatus.DONE
    assert FEISHU_TO_STATUS["canceled"] == IssueStatus.CANCELED


def test_status_to_feishu_mapping():
    assert STATUS_TO_FEISHU[IssueStatus.TODO] == "not_started"
    assert STATUS_TO_FEISHU[IssueStatus.IN_PROGRESS] == "in_progress"
    assert STATUS_TO_FEISHU[IssueStatus.DONE] == "completed"
    assert STATUS_TO_FEISHU[IssueStatus.CANCELED] == "canceled"
    assert STATUS_TO_FEISHU[IssueStatus.BACKLOG] == "not_started"
    assert STATUS_TO_FEISHU[IssueStatus.IN_REVIEW] == "in_progress"


def test_feishu_priority_mapping():
    assert FEISHU_TO_PRIORITY[1] == IssuePriority.LOW
    assert FEISHU_TO_PRIORITY[2] == IssuePriority.MEDIUM
    assert FEISHU_TO_PRIORITY[3] == IssuePriority.HIGH


# ---------------------------------------------------------------------------
# token refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_auto_refresh(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        # First auth
        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        fetch_resp = MagicMock()
        fetch_resp.json.return_value = _task_list_response()
        fetch_resp.raise_for_status = MagicMock()
        fetch_resp.status_code = 200

        # Second auth (for refresh)
        refresh_resp = MagicMock()
        refresh_resp.json.return_value = {
            "code": 0,
            "tenant_access_token": "t-refreshed",
            "expire": 7200,
        }
        refresh_resp.raise_for_status = MagicMock()

        mock_http.post.side_effect = [auth_resp, refresh_resp]
        mock_http.request.return_value = fetch_resp

        await client.initialize()
        # Force token expiry
        client._token_expires_at = time.monotonic() - 1

        issues = await client.fetch_issues()
        assert issues == []
        # Token should have been refreshed
        assert client._token == "t-refreshed"


# ---------------------------------------------------------------------------
# parse helpers
# ---------------------------------------------------------------------------


def test_extract_plain_text():
    desc = {"rich_text": [{"type": "text", "text": "Hello "}, {"type": "text", "text": "World"}]}
    assert _extract_plain_text(desc) == "Hello World"


def test_extract_plain_text_none():
    assert _extract_plain_text(None) is None


def test_extract_plain_text_empty():
    assert _extract_plain_text({}) is None


def test_parse_task_identifier_fallback(client):
    task = _sample_task(guid="guid-abcdef123456")
    task.pop("custom_identifier", None)
    issue = client._parse_task(task)
    # Falls back to first 8 chars of task_guid
    assert issue.identifier == "guid-abc"


def test_parse_task_custom_identifier(client):
    task = _sample_task()
    task["custom_identifier"] = "FEISHU-42"
    issue = client._parse_task(task)
    assert issue.identifier == "FEISHU-42"


# ---------------------------------------------------------------------------
# API error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_error_handling(client):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value = mock_http

        auth_resp = MagicMock()
        auth_resp.json.return_value = _auth_response()
        auth_resp.raise_for_status = MagicMock()

        error_resp = MagicMock()
        error_resp.json.return_value = {"code": 9999, "msg": "server error", "data": {}}
        error_resp.raise_for_status = MagicMock()
        error_resp.status_code = 200

        mock_http.post.return_value = auth_resp
        mock_http.request.return_value = error_resp

        await client.initialize()
        result = await client.update_status("guid-1", IssueStatus.DONE)

    assert result is False
