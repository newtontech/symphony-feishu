"""Feishu authentication and API client base."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import abstractmethod
from typing import Any

import httpx

from symphony.config import TrackerConfig
from symphony.models import Issue, IssueStatus
from symphony.tracker.base import IssueTracker

logger = logging.getLogger(__name__)

# Feishu API endpoints
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
FEISHU_AUTH_URL = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"

# Default token TTL buffer (refresh 5 minutes before expiry)
TOKEN_REFRESH_BUFFER_SECONDS = 300


class FeishuAuthError(Exception):
    """Feishu authentication error."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Feishu auth error {code}: {message}")


class FeishuAPIError(Exception):
    """Feishu API error."""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"Feishu API error {code}: {message}")


class FeishuRateLimitError(FeishuAPIError):
    """Feishu rate limit error."""

    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(99991400, "Rate limit exceeded")


class FeishuTokenManager:
    """Manages Feishu tenant access token with auto-refresh."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        refresh_buffer_seconds: int = TOKEN_REFRESH_BUFFER_SECONDS,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.refresh_buffer_seconds = refresh_buffer_seconds

        self._token: str | None = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()

    @property
    def is_valid(self) -> bool:
        """Check if current token is valid and not near expiry."""
        if not self._token:
            return False
        return time.time() < (self._expires_at - self.refresh_buffer_seconds)

    async def get_token(self, client: httpx.AsyncClient) -> str:
        """Get a valid token, refreshing if necessary."""
        async with self._lock:
            if self.is_valid:
                return self._token  # type: ignore

            await self._refresh_token(client)
            return self._token  # type: ignore

    async def _refresh_token(self, client: httpx.AsyncClient) -> None:
        """Refresh the tenant access token."""
        logger.info("Refreshing Feishu tenant access token")

        response = await client.post(
            FEISHU_AUTH_URL,
            json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
        )

        data = response.json()

        if data.get("code") != 0:
            raise FeishuAuthError(
                code=data.get("code", -1),
                message=data.get("msg", "Unknown error"),
            )

        self._token = data["tenant_access_token"]
        self._expires_at = time.time() + data.get("expire", 7200)

        logger.info(f"Token refreshed, expires in {data.get('expire', 7200)} seconds")

    def invalidate(self) -> None:
        """Invalidate the current token."""
        self._token = None
        self._expires_at = 0


class FeishuBaseTracker(IssueTracker):
    """Base class for Feishu trackers with common functionality."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        base_url: str = FEISHU_API_BASE,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url

        self._client: httpx.AsyncClient | None = None
        self._token_manager = FeishuTokenManager(app_id, app_secret)

    async def initialize(self) -> None:
        """Initialize the Feishu client."""
        if not self.app_id or not self.app_secret:
            raise ValueError("FEISHU_APP_ID and FEISHU_APP_SECRET are required")

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            headers={
                "Content-Type": "application/json",
            },
        )

        # Pre-fetch token to validate credentials
        await self._token_manager.get_token(self._client)
        logger.info("Feishu client initialized successfully")

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to Feishu API."""
        if not self._client:
            raise RuntimeError("Client not initialized. Call initialize() first.")

        token = await self._token_manager.get_token(self._client)

        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = await self._client.request(
                method,
                path,
                headers=headers,
                json=json,
                params=params,
            )

            data = response.json()

            # Handle API errors
            code = data.get("code", 0)
            if code != 0:
                # Check for rate limit
                if code == 99991400:
                    raise FeishuRateLimitError(retry_after=60)

                # Check for token expiry
                if code == 99991663:
                    self._token_manager.invalidate()
                    # Retry once with new token
                    return await self._request(method, path, json=json, params=params)

                raise FeishuAPIError(
                    code=code,
                    message=data.get("msg", "Unknown error"),
                    data=data.get("data"),
                )

            return data

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e}")
            raise FeishuAPIError(
                code=e.response.status_code,
                message=str(e),
            )

    # Abstract methods that subclasses must implement
    @abstractmethod
    async def fetch_issues(
        self,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[Issue]:
        """Fetch issues from the tracker."""
        pass

    @abstractmethod
    async def get_issue(self, issue_id: str) -> Issue | None:
        """Get a single issue by ID."""
        pass

    @abstractmethod
    async def update_status(self, issue_id: str, status: IssueStatus) -> bool:
        """Update the status of an issue."""
        pass

    async def add_comment(self, issue_id: str, comment: str) -> bool:
        """Add a comment to an issue.

        Default implementation returns False.
        Subclasses can override if supported.
        """
        logger.warning("add_comment not implemented for this tracker")
        return False

    async def add_labels(self, issue_id: str, labels: list[str]) -> bool:
        """Add labels to an issue.

        Default implementation returns False.
        Subclasses can override if supported.
        """
        logger.warning("add_labels not implemented for this tracker")
        return False