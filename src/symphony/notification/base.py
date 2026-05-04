"""Abstract base class for notification providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NotificationLevel(str, Enum):
    """Notification severity level."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotificationEvent(BaseModel):
    """A structured notification event."""

    title: str
    message: str
    level: NotificationLevel = NotificationLevel.INFO
    issue_id: str | None = None
    issue_identifier: str | None = None
    issue_title: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    workspace_path: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CardAction(BaseModel):
    """An action button on an interactive card."""

    label: str
    action: str
    value: dict[str, Any] = Field(default_factory=dict)
    style: str = "primary"  # primary, danger, default


class Notifier(ABC):
    """Abstract interface for notification providers."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the notifier (validate credentials, etc.)."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Cleanup resources."""
        pass

    @abstractmethod
    async def send(
        self,
        event: NotificationEvent,
        *,
        chat_id: str | None = None,
        user_id: str | None = None,
    ) -> str | None:
        """Send a text notification.

        Args:
            event: The notification event.
            chat_id: Target group chat ID (None uses default).
            user_id: Target user open_id (sends DM).

        Returns:
            Message ID if successful, None otherwise.
        """
        pass

    @abstractmethod
    async def send_card(
        self,
        event: NotificationEvent,
        actions: list[CardAction] | None = None,
        *,
        chat_id: str | None = None,
        user_id: str | None = None,
    ) -> str | None:
        """Send an interactive card notification.

        Args:
            event: The notification event.
            actions: Optional action buttons.
            chat_id: Target group chat ID.
            user_id: Target user open_id.

        Returns:
            Message ID if successful, None otherwise.
        """
        pass

    @abstractmethod
    async def reply(
        self,
        message_id: str,
        event: NotificationEvent,
    ) -> str | None:
        """Reply to an existing message (thread follow-up).

        Args:
            message_id: The parent message ID to reply to.
            event: The follow-up event.

        Returns:
            New message ID if successful, None otherwise.
        """
        pass

    @abstractmethod
    async def update_card(
        self,
        message_id: str,
        event: NotificationEvent,
        actions: list[CardAction] | None = None,
    ) -> bool:
        """Update an existing card message.

        Args:
            message_id: The card message ID to update.
            event: Updated event data.
            actions: Updated action buttons.

        Returns:
            True if successful.
        """
        pass

    @abstractmethod
    async def handle_callback(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle an interactive card callback.

        Args:
            payload: The callback payload from the notification provider.

        Returns:
            Response to send back.
        """
        pass
