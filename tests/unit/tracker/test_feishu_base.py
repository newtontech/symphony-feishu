"""Tests for Feishu base tracker."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from symphony.tracker.feishu_base import (
    FEISHU_AUTH_URL,
    FeishuAPIError,
    FeishuAuthError,
    FeishuBaseTracker,
    FeishuRateLimitError,
    FeishuTokenManager,
)
from symphony.models import Issue, IssueStatus


class ConcreteFeishuTracker(FeishuBaseTracker):
    """Concrete implementation for testing."""

    async def fetch_issues(
        self,
        limit: int = 10,
        filter: dict[str, str] | None = None,
    ) -> list[Issue]:
        """Test implementation."""
        return []

    async def get_issue(self, issue_id: str) -> Issue | None:
        """Test implementation."""
        return None

    async def update_status(self, issue_id: str, status: IssueStatus) -> bool:
        """Test implementation."""
        return True


class TestFeishuTokenManager:
    """Tests for FeishuTokenManager."""

    def test_init(self):
        """Test token manager initialization."""
        manager = FeishuTokenManager("app_id", "app_secret")
        assert manager.app_id == "app_id"
        assert manager.app_secret == "app_secret"
        assert manager._token is None
        assert manager._expires_at == 0

    def test_is_valid_no_token(self):
        """Test is_valid returns False when no token."""
        manager = FeishuTokenManager("app_id", "app_secret")
        assert manager.is_valid is False

    def test_is_valid_expired_token(self):
        """Test is_valid returns False when token expired."""
        manager = FeishuTokenManager("app_id", "app_secret")
        manager._token = "test_token"
        manager._expires_at = time.time() - 100  # Expired
        assert manager.is_valid is False

    def test_is_valid_near_expiry(self):
        """Test is_valid returns False when token near expiry."""
        manager = FeishuTokenManager("app_id", "app_secret", refresh_buffer_seconds=300)
        manager._token = "test_token"
        manager._expires_at = time.time() + 100  # Expires in 100s, buffer is 300s
        assert manager.is_valid is False

    def test_is_valid_success(self):
        """Test is_valid returns True for valid token."""
        manager = FeishuTokenManager("app_id", "app_secret", refresh_buffer_seconds=300)
        manager._token = "test_token"
        manager._expires_at = time.time() + 1000  # Expires in 1000s
        assert manager.is_valid is True

    def test_invalidate(self):
        """Test token invalidation."""
        manager = FeishuTokenManager("app_id", "app_secret")
        manager._token = "test_token"
        manager._expires_at = time.time() + 1000

        manager.invalidate()

        assert manager._token is None
        assert manager._expires_at == 0

    @pytest.mark.asyncio
    async def test_get_token_refresh(self):
        """Test token refresh on get_token."""
        manager = FeishuTokenManager("app_id", "app_secret")

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "tenant_access_token": "new_token",
            "expire": 7200,
        }
        mock_client.post.return_value = mock_response

        token = await manager.get_token(mock_client)

        assert token == "new_token"
        assert manager._token == "new_token"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_token_cached(self):
        """Test get_token returns cached valid token."""
        manager = FeishuTokenManager("app_id", "app_secret")
        manager._token = "cached_token"
        manager._expires_at = time.time() + 1000

        mock_client = AsyncMock(spec=httpx.AsyncClient)

        token = await manager.get_token(mock_client)

        assert token == "cached_token"
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_token_auth_error(self):
        """Test refresh_token raises auth error."""
        manager = FeishuTokenManager("invalid_id", "invalid_secret")

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 10003,
            "msg": "Invalid app_id or app_secret",
        }
        mock_client.post.return_value = mock_response

        with pytest.raises(FeishuAuthError) as exc_info:
            await manager.get_token(mock_client)

        assert exc_info.value.code == 10003
        assert "Invalid" in exc_info.value.message


class TestFeishuAuthError:
    """Tests for FeishuAuthError."""

    def test_init(self):
        """Test error initialization."""
        error = FeishuAuthError(10003, "Invalid credentials")
        assert error.code == 10003
        assert error.message == "Invalid credentials"
        assert "10003" in str(error)
        assert "Invalid credentials" in str(error)


class TestFeishuAPIError:
    """Tests for FeishuAPIError."""

    def test_init(self):
        """Test error initialization."""
        error = FeishuAPIError(10001, "Not found", {"detail": "resource not found"})
        assert error.code == 10001
        assert error.message == "Not found"
        assert error.data == {"detail": "resource not found"}

    def test_init_no_data(self):
        """Test error initialization without data."""
        error = FeishuAPIError(10001, "Not found")
        assert error.code == 10001
        assert error.message == "Not found"
        assert error.data is None


class TestFeishuRateLimitError:
    """Tests for FeishuRateLimitError."""

    def test_init(self):
        """Test error initialization."""
        error = FeishuRateLimitError(retry_after=30)
        assert error.retry_after == 30
        assert error.code == 99991400


class TestFeishuBaseTracker:
    """Tests for FeishuBaseTracker."""

    def test_init(self):
        """Test tracker initialization."""
        tracker = ConcreteFeishuTracker("app_id", "app_secret")
        assert tracker.app_id == "app_id"
        assert tracker.app_secret == "app_secret"
        assert tracker._client is None

    def test_init_custom_base_url(self):
        """Test tracker initialization with custom base URL."""
        tracker = ConcreteFeishuTracker(
            "app_id",
            "app_secret",
            base_url="https://custom.api.com",
        )
        assert tracker.base_url == "https://custom.api.com"

    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test tracker initialization."""
        tracker = ConcreteFeishuTracker("app_id", "app_secret")

        with patch.object(
            tracker._token_manager,
            "get_token",
            new_callable=AsyncMock,
            return_value="test_token",
        ):
            await tracker.initialize()

        assert tracker._client is not None
        await tracker.close()

    @pytest.mark.asyncio
    async def test_initialize_missing_credentials(self):
        """Test initialization fails with missing credentials."""
        tracker = ConcreteFeishuTracker("", "")

        with pytest.raises(ValueError) as exc_info:
            await tracker.initialize()

        assert "FEISHU_APP_ID" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_close(self):
        """Test tracker close."""
        tracker = ConcreteFeishuTracker("app_id", "app_secret")

        with patch.object(
            tracker._token_manager,
            "get_token",
            new_callable=AsyncMock,
            return_value="test_token",
        ):
            await tracker.initialize()
            await tracker.close()

        assert tracker._client is None

    @pytest.mark.asyncio
    async def test_request_not_initialized(self):
        """Test _request fails if not initialized."""
        tracker = ConcreteFeishuTracker("app_id", "app_secret")

        with pytest.raises(RuntimeError) as exc_info:
            await tracker._request("GET", "/test")

        assert "not initialized" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_request_success(self):
        """Test successful API request."""
        tracker = ConcreteFeishuTracker("app_id", "app_secret")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "data": {"result": "success"},
        }

        with patch.object(
            tracker._token_manager,
            "get_token",
            new_callable=AsyncMock,
            return_value="test_token",
        ):
            await tracker.initialize()

            with patch.object(
                tracker._client,
                "request",
                new_callable=AsyncMock,
                return_value=mock_response,
            ):
                result = await tracker._request("GET", "/test")

        assert result["code"] == 0
        assert result["data"]["result"] == "success"
        await tracker.close()

    @pytest.mark.asyncio
    async def test_request_api_error(self):
        """Test API request with error response."""
        tracker = ConcreteFeishuTracker("app_id", "app_secret")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 10001,
            "msg": "Resource not found",
        }

        with patch.object(
            tracker._token_manager,
            "get_token",
            new_callable=AsyncMock,
            return_value="test_token",
        ):
            await tracker.initialize()

            with patch.object(
                tracker._client,
                "request",
                new_callable=AsyncMock,
                return_value=mock_response,
            ):
                with pytest.raises(FeishuAPIError) as exc_info:
                    await tracker._request("GET", "/test")

        assert exc_info.value.code == 10001
        await tracker.close()

    @pytest.mark.asyncio
    async def test_request_rate_limit(self):
        """Test API request with rate limit."""
        tracker = ConcreteFeishuTracker("app_id", "app_secret")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 99991400,
            "msg": "Rate limit exceeded",
        }

        with patch.object(
            tracker._token_manager,
            "get_token",
            new_callable=AsyncMock,
            return_value="test_token",
        ):
            await tracker.initialize()

            with patch.object(
                tracker._client,
                "request",
                new_callable=AsyncMock,
                return_value=mock_response,
            ):
                with pytest.raises(FeishuRateLimitError):
                    await tracker._request("GET", "/test")

        await tracker.close()

    @pytest.mark.asyncio
    async def test_request_token_expiry_retry(self):
        """Test API request retries on token expiry."""
        tracker = ConcreteFeishuTracker("app_id", "app_secret")

        # First call: token expired
        mock_response_expired = MagicMock()
        mock_response_expired.json.return_value = {
            "code": 99991663,
            "msg": "Token expired",
        }

        # Second call: success
        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {
            "code": 0,
            "data": {"result": "success"},
        }

        with patch.object(
            tracker._token_manager,
            "get_token",
            new_callable=AsyncMock,
            return_value="test_token",
        ):
            tracker._token_manager._token = "old_token"
            tracker._token_manager._expires_at = time.time() + 1000

            await tracker.initialize()

            with patch.object(
                tracker._client,
                "request",
                new_callable=AsyncMock,
                side_effect=[mock_response_expired, mock_response_success],
            ):
                result = await tracker._request("GET", "/test")

        assert result["code"] == 0
        assert tracker._token_manager._token is None  # Token was invalidated
        await tracker.close()

    @pytest.mark.asyncio
    async def test_add_comment_not_implemented(self):
        """Test add_comment returns False by default."""
        tracker = ConcreteFeishuTracker("app_id", "app_secret")

        with patch.object(
            tracker._token_manager,
            "get_token",
            new_callable=AsyncMock,
            return_value="test_token",
        ):
            await tracker.initialize()
            result = await tracker.add_comment("issue_id", "comment")

        assert result is False
        await tracker.close()

    @pytest.mark.asyncio
    async def test_add_labels_not_implemented(self):
        """Test add_labels returns False by default."""
        tracker = ConcreteFeishuTracker("app_id", "app_secret")

        with patch.object(
            tracker._token_manager,
            "get_token",
            new_callable=AsyncMock,
            return_value="test_token",
        ):
            await tracker.initialize()
            result = await tracker.add_labels("issue_id", ["label1"])

        assert result is False
        await tracker.close()