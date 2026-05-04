"""Feishu Task v2 API client."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from symphony.config import TrackerConfig
from symphony.models import Issue, IssuePriority, IssueStatus
from symphony.tracker.base import IssueTracker

logger = logging.getLogger(__name__)

# Status mapping: Feishu -> IssueStatus
FEISHU_TO_STATUS: dict[str, IssueStatus] = {
    "not_started": IssueStatus.TODO,
    "in_progress": IssueStatus.IN_PROGRESS,
    "completed": IssueStatus.DONE,
    "canceled": IssueStatus.CANCELED,
}

# Status mapping: IssueStatus -> Feishu
STATUS_TO_FEISHU: dict[IssueStatus, str] = {
    IssueStatus.BACKLOG: "not_started",
    IssueStatus.TODO: "not_started",
    IssueStatus.IN_PROGRESS: "in_progress",
    IssueStatus.IN_REVIEW: "in_progress",
    IssueStatus.DONE: "completed",
    IssueStatus.CANCELED: "canceled",
}

# Priority mapping: Feishu int -> IssuePriority
FEISHU_TO_PRIORITY: dict[int, IssuePriority] = {
    1: IssuePriority.LOW,
    2: IssuePriority.MEDIUM,
    3: IssuePriority.HIGH,
}


def _extract_plain_text(description: dict[str, Any] | None) -> str | None:
    """Extract plain text from Feishu rich_text description."""
    if not description:
        return None
    rich_text = description.get("rich_text")
    if not rich_text or not isinstance(rich_text, list):
        return None
    parts: list[str] = []
    for block in rich_text:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts) or None


class FeishuClient(IssueTracker):
    """Feishu Task v2 API client.

    Rate limit: 10 requests/second per app.
    """

    def __init__(self, config: TrackerConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def _base_url(self) -> str:
        return self.config.feishu_base_url.rstrip("/")

    async def initialize(self) -> None:
        """Initialize the Feishu client and authenticate."""
        if not self.config.feishu_app_id:
            raise ValueError("FEISHU_APP_ID is required (set SYMPHONY_TRACKER_FEISHU_APP_ID)")
        if not self.config.feishu_app_secret:
            raise ValueError(
                "FEISHU_APP_SECRET is required (set SYMPHONY_TRACKER_FEISHU_APP_SECRET)"
            )

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=30.0,
        )
        await self._refresh_token()
        logger.info("Feishu client initialized")

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _refresh_token(self) -> None:
        """Obtain a new tenant_access_token."""
        if not self._client:
            raise RuntimeError("Client not initialized")

        resp = await self._client.post(
            "/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.config.feishu_app_id,
                "app_secret": self.config.feishu_app_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code", -1) != 0:
            raise RuntimeError(f"Feishu auth failed: {data.get('msg', 'unknown error')}")

        self._token = data["tenant_access_token"]
        # Refresh 300s before actual expiry
        expire = data.get("expire", 7200)
        self._token_expires_at = time.monotonic() + expire - 300
        logger.debug("Feishu token refreshed, expires in %ds", expire)

    async def _ensure_token(self) -> None:
        """Refresh token if expired."""
        if time.monotonic() >= self._token_expires_at:
            await self._refresh_token()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request with auto-refresh on 401."""
        if not self._client:
            raise RuntimeError("Client not initialized")

        await self._ensure_token()

        headers = {"Authorization": f"Bearer {self._token}"}
        resp = await self._client.request(
            method, path, json=json, params=params, headers=headers
        )

        if resp.status_code == 401:
            await self._refresh_token()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = await self._client.request(
                method, path, json=json, params=params, headers=headers
            )

        resp.raise_for_status()
        data = resp.json()

        if data.get("code", -1) != 0:
            raise RuntimeError(f"Feishu API error: code={data.get('code')} msg={data.get('msg')}")

        return data.get("data", {})

    async def fetch_issues(
        self,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[Issue]:
        """Fetch tasks from Feishu task list."""
        params: dict[str, Any] = {"page_size": min(limit, 50)}

        if self.config.feishu_tasklist_id:
            params["tasklist_guid"] = self.config.feishu_tasklist_id

        if filter:
            if "status" in filter:
                params["status"] = filter["status"]

        data = await self._request("GET", "/open-apis/task/v2/tasks", params=params)
        items = data.get("items", [])
        return [self._parse_task(item) for item in items[:limit]]

    async def get_issue(self, issue_id: str) -> Issue | None:
        """Get a single task by GUID."""
        try:
            data = await self._request("GET", f"/open-apis/task/v2/tasks/{issue_id}")
        except RuntimeError as e:
            logger.warning("Failed to get task %s: %s", issue_id, e)
            return None

        task = data.get("task")
        if not task:
            return None

        return self._parse_task(task)

    async def update_status(
        self,
        issue_id: str,
        status: IssueStatus,
    ) -> bool:
        """Update task status."""
        feishu_status = STATUS_TO_FEISHU.get(status)
        if not feishu_status:
            logger.warning("Cannot map status %s to Feishu", status)
            return False

        try:
            await self._request(
                "PATCH",
                f"/open-apis/task/v2/tasks/{issue_id}",
                json={"status": feishu_status},
            )
            logger.info("Updated task %s status to %s", issue_id, feishu_status)
            return True
        except RuntimeError as e:
            logger.error("Failed to update task %s status: %s", issue_id, e)
            return False

    async def add_comment(
        self,
        issue_id: str,
        comment: str,
    ) -> bool:
        """Add a comment to a task."""
        try:
            await self._request(
                "POST",
                f"/open-apis/task/v2/tasks/{issue_id}/comments",
                json={
                    "content": {
                        "rich_text": [{"type": "text", "text": comment}]
                    }
                },
            )
            logger.info("Added comment to task %s", issue_id)
            return True
        except RuntimeError as e:
            logger.error("Failed to add comment to task %s: %s", issue_id, e)
            return False

    async def add_labels(
        self,
        issue_id: str,
        labels: list[str],
    ) -> bool:
        """Feishu tasks do not support labels via API."""
        logger.warning("Label management not supported for Feishu tasks")
        return False

    def _parse_task(self, data: dict[str, Any]) -> Issue:
        """Parse Feishu task data into Issue model."""
        feishu_status = data.get("status", "not_started")
        status = FEISHU_TO_STATUS.get(feishu_status, IssueStatus.TODO)

        priority_num = data.get("priority")
        priority = FEISHU_TO_PRIORITY.get(priority_num, IssuePriority.NONE) if priority_num else IssuePriority.NONE

        task_guid = data.get("task_guid", "")
        custom_id = data.get("custom_identifier")
        identifier = custom_id if custom_id else (task_guid[:8] if task_guid else "unknown")

        tags = data.get("tags", [])
        if isinstance(tags, list):
            labels = [t if isinstance(t, str) else str(t) for t in tags]
        else:
            labels = []

        return Issue(
            id=task_guid,
            identifier=identifier,
            title=data.get("summary", ""),
            description=_extract_plain_text(data.get("description")),
            status=status,
            priority=priority,
            labels=labels,
            assignee_id=None,
            project_id=self.config.feishu_tasklist_id,
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )
