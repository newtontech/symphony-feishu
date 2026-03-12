"""Abstract base class for issue trackers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from symphony.models import Issue, IssueStatus


class IssueTracker(ABC):
    """Abstract interface for issue trackers."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the tracker client.

        Should validate credentials and setup connections.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the tracker client and cleanup resources."""
        pass

    @abstractmethod
    async def fetch_issues(
        self,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[Issue]:
        """Fetch issues from the tracker.

        Args:
            limit: Maximum number of issues to fetch
            filter: Optional filter criteria

        Returns:
            List of issues matching criteria
        """
        pass

    @abstractmethod
    async def get_issue(self, issue_id: str) -> Issue | None:
        """Get a single issue by ID.

        Args:
            issue_id: Issue identifier

        Returns:
            Issue if found, None otherwise
        """
        pass

    @abstractmethod
    async def update_status(
        self,
        issue_id: str,
        status: IssueStatus,
    ) -> bool:
        """Update the status of an issue.

        Args:
            issue_id: Issue identifier
            status: New status

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def add_comment(
        self,
        issue_id: str,
        comment: str,
    ) -> bool:
        """Add a comment to an issue.

        Args:
            issue_id: Issue identifier
            comment: Comment text

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def add_labels(
        self,
        issue_id: str,
        labels: list[str],
    ) -> bool:
        """Add labels to an issue.

        Args:
            issue_id: Issue identifier
            labels: Labels to add

        Returns:
            True if successful, False otherwise
        """
        pass
