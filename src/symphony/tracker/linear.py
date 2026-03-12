"""Linear GraphQL API client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from symphony.config import TrackerConfig
from symphony.models import Issue, IssuePriority, IssueStatus
from symphony.tracker.base import IssueTracker

logger = logging.getLogger(__name__)

# Linear GraphQL endpoints
LINEAR_API_URL = "https://api.linear.app/graphql"

# GraphQL queries and mutations
FETCH_ISSUES_QUERY = """
query FetchIssues($filter: IssueFilter, $first: Int) {
    issues(filter: $filter, first: $first) {
        nodes {
            id
            identifier
            title
            description
            state {
                name
                type
            }
            priority
            labels {
                nodes {
                    name
                }
            }
            assignee {
                id
            }
            project {
                id
            }
            createdAt
            updatedAt
        }
        pageInfo {
            hasNextPage
            endCursor
        }
    }
}
"""

GET_ISSUE_QUERY = """
query GetIssue($id: String!) {
    issue(id: $id) {
        id
        identifier
        title
        description
        state {
            name
            type
        }
        priority
        labels {
            nodes {
                name
            }
        }
        assignee {
            id
        }
        project {
            id
        }
        createdAt
        updatedAt
    }
}
"""

UPDATE_STATUS_MUTATION = """
mutation UpdateIssueStatus($id: String!, $stateId: String!) {
    issueUpdate(id: $id, input: { stateId: $stateId }) {
        success
        issue {
            id
            state {
                name
            }
        }
    }
}
"""

ADD_COMMENT_MUTATION = """
mutation AddComment($issueId: String!, $body: String!) {
    commentCreate(input: { issueId: $issueId, body: $body }) {
        success
        comment {
            id
        }
    }
}
"""

# State mapping for Linear
STATE_MAPPING: dict[IssueStatus, str] = {
    IssueStatus.BACKLOG: "backlog",
    IssueStatus.TODO: "todo",
    IssueStatus.IN_PROGRESS: "in_progress",
    IssueStatus.IN_REVIEW: "in_review",
    IssueStatus.DONE: "done",
    IssueStatus.CANCELED: "canceled",
}

PRIORITY_MAPPING: dict[int, IssuePriority] = {
    0: IssuePriority.NONE,
    1: IssuePriority.URGENT,
    2: IssuePriority.HIGH,
    3: IssuePriority.MEDIUM,
    4: IssuePriority.LOW,
}


class LinearClient(IssueTracker):
    """Linear GraphQL API client."""

    def __init__(self, config: TrackerConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._state_cache: dict[str, str] = {}  # state name -> state id

    async def initialize(self) -> None:
        """Initialize the Linear client."""
        if not self.config.linear_api_key:
            raise ValueError("LINEAR_API_KEY is required")

        self._client = httpx.AsyncClient(
            base_url=self.config.linear_api_url,
            headers={
                "Authorization": f"Bearer {self.config.linear_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

        # Fetch and cache workflow states
        await self._cache_workflow_states()
        logger.info("Linear client initialized")

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_issues(
        self,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[Issue]:
        """Fetch issues from Linear."""
        if not self._client:
            raise RuntimeError("Client not initialized")

        # Build filter
        linear_filter = self._build_filter(filter)

        response = await self._client.post(
            "/",
            json={
                "query": FETCH_ISSUES_QUERY,
                "variables": {
                    "filter": linear_filter,
                    "first": limit,
                },
            },
        )

        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            raise RuntimeError(f"GraphQL error: {data['errors']}")

        nodes = data.get("data", {}).get("issues", {}).get("nodes", [])
        return [self._parse_issue(node) for node in nodes]

    async def get_issue(self, issue_id: str) -> Issue | None:
        """Get a single issue by ID."""
        if not self._client:
            raise RuntimeError("Client not initialized")

        response = await self._client.post(
            "/",
            json={
                "query": GET_ISSUE_QUERY,
                "variables": {"id": issue_id},
            },
        )

        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            logger.warning(f"Failed to get issue {issue_id}: {data['errors']}")
            return None

        issue_data = data.get("data", {}).get("issue")
        if not issue_data:
            return None

        return self._parse_issue(issue_data)

    async def update_status(
        self,
        issue_id: str,
        status: IssueStatus,
    ) -> bool:
        """Update issue status."""
        if not self._client:
            raise RuntimeError("Client not initialized")

        state_name = STATE_MAPPING.get(status)
        if not state_name:
            logger.warning(f"Unknown status: {status}")
            return False

        state_id = self._state_cache.get(state_name)
        if not state_id:
            logger.warning(f"State not found: {state_name}")
            return False

        response = await self._client.post(
            "/",
            json={
                "query": UPDATE_STATUS_MUTATION,
                "variables": {
                    "id": issue_id,
                    "stateId": state_id,
                },
            },
        )

        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            logger.error(f"Failed to update status: {data['errors']}")
            return False

        return data.get("data", {}).get("issueUpdate", {}).get("success", False)

    async def add_comment(
        self,
        issue_id: str,
        comment: str,
    ) -> bool:
        """Add a comment to an issue."""
        if not self._client:
            raise RuntimeError("Client not initialized")

        response = await self._client.post(
            "/",
            json={
                "query": ADD_COMMENT_MUTATION,
                "variables": {
                    "issueId": issue_id,
                    "body": comment,
                },
            },
        )

        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            logger.error(f"Failed to add comment: {data['errors']}")
            return False

        return data.get("data", {}).get("commentCreate", {}).get("success", False)

    async def add_labels(
        self,
        issue_id: str,
        labels: list[str],
    ) -> bool:
        """Add labels to an issue.

        Note: Linear label management is more complex, this is a simplified version.
        """
        logger.warning("Label management not fully implemented for Linear")
        return False

    def _build_filter(self, filter: dict[str, Any] | None) -> dict[str, Any]:
        """Build Linear filter from generic filter dict."""
        linear_filter: dict[str, Any] = {}

        if not filter:
            # Default filter: unassigned, non-completed issues
            linear_filter["state"] = {"type": {"neq": "completed"}}
            linear_filter["assignee"] = {"null": True}
        else:
            if "team_id" in filter or self.config.linear_team_id:
                linear_filter["team"] = {"id": {"eq": filter.get("team_id") or self.config.linear_team_id}}

            if "project_id" in filter or self.config.linear_project_id:
                linear_filter["project"] = {"id": {"eq": filter.get("project_id") or self.config.linear_project_id}}

            if "labels" in filter:
                linear_filter["labels"] = {"name": {"in": filter["labels"]}}

            if "priority" in filter:
                linear_filter["priority"] = {"eq": filter["priority"]}

        return linear_filter

    def _parse_issue(self, data: dict[str, Any]) -> Issue:
        """Parse Linear issue data into Issue model."""
        state = data.get("state", {})
        state_type = state.get("type", "").lower()

        # Map Linear state type to IssueStatus
        status_map = {
            "backlog": IssueStatus.BACKLOG,
            "unstarted": IssueStatus.TODO,
            "started": IssueStatus.IN_PROGRESS,
            "completed": IssueStatus.DONE,
            "canceled": IssueStatus.CANCELED,
        }
        status = status_map.get(state_type, IssueStatus.TODO)

        # Parse priority
        priority_num = data.get("priority", 0)
        priority = PRIORITY_MAPPING.get(priority_num, IssuePriority.NONE)

        # Extract labels
        labels = [
            label["name"]
            for label in data.get("labels", {}).get("nodes", [])
        ]

        return Issue(
            id=data["id"],
            identifier=data["identifier"],
            title=data["title"],
            description=data.get("description"),
            status=status,
            priority=priority,
            labels=labels,
            assignee_id=data.get("assignee", {}).get("id") if data.get("assignee") else None,
            project_id=data.get("project", {}).get("id") if data.get("project") else None,
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )

    async def _cache_workflow_states(self) -> None:
        """Fetch and cache workflow states."""
        query = """
        query GetWorkflowStates {
            workflowStates {
                nodes {
                    id
                    name
                    type
                }
            }
        }
        """

        if not self._client:
            return

        try:
            response = await self._client.post("/", json={"query": query})
            response.raise_for_status()
            data = response.json()

            nodes = data.get("data", {}).get("workflowStates", {}).get("nodes", [])
            for node in nodes:
                # Map by name (normalized)
                name = node["name"].lower().replace(" ", "_")
                self._state_cache[name] = node["id"]
                # Also map by type
                self._state_cache[node["type"].lower()] = node["id"]

            logger.info(f"Cached {len(nodes)} workflow states")

        except Exception as e:
            logger.warning(f"Failed to cache workflow states: {e}")
