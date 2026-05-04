"""Core orchestration engine."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from tenacity import (
    AsyncRetrying,
    RetryError,
    stop_after_attempt,
    wait_exponential,
)

from symphony.config import Config
from symphony.models import (
    Issue,
    IssueStatus,
    Metrics,
    OrchestratorState,
    OrchestratorStatus,
    Workspace,
    WorkspaceState,
    Workflow,
)
from symphony.notification.base import (
    CardAction,
    NotificationEvent,
    NotificationLevel,
)

if TYPE_CHECKING:
    from symphony.agent_runner import AgentRunner
    from symphony.notification.base import Notifier
    from symphony.tracker.base import IssueTracker
    from symphony.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main orchestration engine that coordinates all components."""

    def __init__(
        self,
        config: Config,
        workflow: Workflow,
        tracker: IssueTracker,
        workspace_manager: WorkspaceManager,
        agent_runner: AgentRunner,
        notifier: Notifier | None = None,
    ):
        self.config = config
        self.workflow = workflow
        self.tracker = tracker
        self.workspace_manager = workspace_manager
        self.agent_runner = agent_runner
        self.notifier = notifier

        self._state = OrchestratorState.STOPPED
        self._task: asyncio.Task[None] | None = None
        self._active_workspaces: dict[UUID, Workspace] = {}
        self._issue_notifications: dict[str, str] = {}
        self._metrics = Metrics()
        self._start_time: float | None = None
        self._last_poll_time: str | None = None
        self._error: str | None = None

    @property
    def state(self) -> OrchestratorState:
        """Current orchestrator state."""
        return self._state

    @property
    def metrics(self) -> Metrics:
        """Current metrics."""
        return self._metrics

    def get_status(self) -> OrchestratorStatus:
        """Get current orchestrator status."""
        uptime = 0.0
        if self._start_time:
            uptime = time.time() - self._start_time

        return OrchestratorStatus(
            state=self._state,
            active_workspaces=len(self._active_workspaces),
            total_completed=self._metrics.total_issues_completed,
            total_failed=self._metrics.total_issues_failed,
            uptime_seconds=uptime,
            current_workflow=self.workflow.config.name,
            last_poll_time=self._last_poll_time,
            error=self._error,
        )

    async def start(self) -> None:
        """Start the orchestrator."""
        if self._state != OrchestratorState.STOPPED:
            logger.warning("Orchestrator already running")
            return

        logger.info("Starting orchestrator")
        self._state = OrchestratorState.STARTING
        self._start_time = time.time()
        self._error = None

        try:
            # Initialize components
            await self.tracker.initialize()
            await self.workspace_manager.initialize()

            # Start main loop
            self._state = OrchestratorState.RUNNING
            self._task = asyncio.create_task(self._run_loop())
            logger.info("Orchestrator started")

        except Exception as e:
            self._state = OrchestratorState.ERROR
            self._error = str(e)
            logger.error(f"Failed to start orchestrator: {e}")
            raise

    async def stop(self) -> None:
        """Stop the orchestrator gracefully."""
        if self._state == OrchestratorState.STOPPED:
            return

        logger.info("Stopping orchestrator")
        self._state = OrchestratorState.STOPPING

        # Cancel main loop
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Wait for active workspaces to complete
        await self._wait_for_workspaces()

        # Cleanup
        await self.tracker.close()
        self._state = OrchestratorState.STOPPED
        logger.info("Orchestrator stopped")

    async def pause(self) -> None:
        """Pause orchestration (finish current work, don't start new)."""
        if self._state == OrchestratorState.RUNNING:
            self._state = OrchestratorState.PAUSED
            logger.info("Orchestrator paused")

    async def resume(self) -> None:
        """Resume orchestration from paused state."""
        if self._state == OrchestratorState.PAUSED:
            self._state = OrchestratorState.RUNNING
            logger.info("Orchestrator resumed")

    async def _run_loop(self) -> None:
        """Main orchestration loop."""
        while self._state in (OrchestratorState.RUNNING, OrchestratorState.PAUSED):
            try:
                if self._state == OrchestratorState.RUNNING:
                    await self._poll_and_process()

                await asyncio.sleep(self.config.poll_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in orchestration loop: {e}")
                self._error = str(e)
                await asyncio.sleep(self.config.poll_interval_seconds)

    async def _poll_and_process(self) -> None:
        """Poll for issues and process them."""
        self._last_poll_time = datetime.now(timezone.utc).isoformat()

        # Check capacity
        max_concurrent = self.workflow.config.max_concurrent
        available_slots = max_concurrent - len(self._active_workspaces)
        if available_slots <= 0:
            logger.debug("No available slots for new workspaces")
            return

        # Fetch issues from tracker
        try:
            issues = await self.tracker.fetch_issues(
                limit=available_slots,
                filter=self.workflow.config.tracker_filter,
            )
        except Exception as e:
            logger.error(f"Failed to fetch issues: {e}")
            return

        if not issues:
            logger.debug("No issues to process")
            return

        logger.info(f"Found {len(issues)} issues to process")

        # Process each issue
        for issue in issues[:available_slots]:
            asyncio.create_task(self._process_issue(issue))

    async def _process_issue(self, issue: Issue) -> None:
        """Process a single issue."""
        logger.info(f"Processing issue {issue.identifier}: {issue.title}")

        try:
            # Create workspace
            workspace = await self.workspace_manager.create(issue)
            self._active_workspaces[workspace.id] = workspace
            self._metrics.total_workspaces_created += 1
            self._metrics.total_issues_processed += 1

            # Update issue status
            await self.tracker.update_status(issue.id, IssueStatus.IN_PROGRESS)

            # Notify: agent started
            await self._notify_issue_start(issue)

            # Run agent with retry
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(self.workflow.config.retry_limit + 1),
                    wait=wait_exponential(
                        multiplier=self.workflow.config.retry_delay_seconds
                    ),
                ):
                    with attempt:
                        await self._run_agent(workspace, issue)
            except RetryError as e:
                raise RuntimeError(f"All retry attempts failed: {e}") from e

            # Mark as completed
            workspace.state = WorkspaceState.COMPLETED
            await self.tracker.update_status(issue.id, IssueStatus.DONE)
            self._metrics.total_issues_completed += 1
            logger.info(f"Issue {issue.identifier} completed successfully")

            # Notify: agent completed
            await self._notify_issue_complete(issue)

        except Exception as e:
            logger.error(f"Failed to process issue {issue.identifier}: {e}")
            self._metrics.total_issues_failed += 1
            try:
                await self.tracker.update_status(issue.id, IssueStatus.TODO)
            except Exception:
                pass

            # Notify: agent failed
            await self._notify_issue_failed(issue, str(e))

        finally:
            # Cleanup workspace
            if workspace.id in self._active_workspaces:
                del self._active_workspaces[workspace.id]
            await self.workspace_manager.cleanup(workspace)

    async def _run_agent(self, workspace: Workspace, issue: Issue) -> None:
        """Run the agent in the workspace."""
        workspace.state = WorkspaceState.RUNNING

        session = await self.agent_runner.run(
            workspace=workspace,
            issue=issue,
            workflow=self.workflow,
        )

        if session.error:
            raise RuntimeError(session.error)

        # Update token metrics
        self._metrics.total_tokens_used += session.tokens_used

    async def _wait_for_workspaces(self) -> None:
        """Wait for active workspaces to complete."""
        if not self._active_workspaces:
            return

        logger.info(
            f"Waiting for {len(self._active_workspaces)} active workspaces"
        )

        # Simple polling - in production, use proper event/condition
        timeout = 300  # 5 minutes
        start = time.time()
        while self._active_workspaces and (time.time() - start) < timeout:
            await asyncio.sleep(1)

        if self._active_workspaces:
            logger.warning(
                f"Timeout waiting for {len(self._active_workspaces)} workspaces"
            )

    # ------------------------------------------------------------------
    # Notification helpers
    # ------------------------------------------------------------------

    async def _notify_issue_start(self, issue: Issue) -> None:
        """Send notification when agent starts working on an issue."""
        if not self.notifier:
            return
        try:
            event = NotificationEvent(
                title=f"Agent started: {issue.identifier}",
                message="Agent is now working on this issue",
                level=NotificationLevel.INFO,
                issue_id=issue.id,
                issue_identifier=issue.identifier,
                issue_title=issue.title,
            )
            actions = None
            if self.config.notification.interactive_approval:
                actions = [
                    CardAction(
                        label="Approve", action="approve",
                        value={"issue_id": issue.id}, style="primary",
                    ),
                    CardAction(
                        label="Reject", action="reject",
                        value={"issue_id": issue.id}, style="danger",
                    ),
                ]
            msg_id = await self.notifier.send_card(event, actions)
            if msg_id:
                self._issue_notifications[issue.id] = msg_id
        except Exception:
            logger.exception("Failed to send start notification for %s", issue.identifier)

    async def _notify_issue_complete(self, issue: Issue) -> None:
        """Send notification when agent completes an issue."""
        if not self.notifier:
            return
        try:
            event = NotificationEvent(
                title=f"Agent completed: {issue.identifier}",
                message=f"Issue completed successfully",
                level=NotificationLevel.SUCCESS,
                issue_id=issue.id,
                issue_identifier=issue.identifier,
                issue_title=issue.title,
            )
            msg_id = self._issue_notifications.pop(issue.id, None)
            if msg_id:
                await self.notifier.update_card(msg_id, event)
            else:
                await self.notifier.send_card(event)
        except Exception:
            logger.exception("Failed to send complete notification for %s", issue.identifier)

    async def _notify_issue_failed(self, issue: Issue, error: str) -> None:
        """Send notification when agent fails on an issue."""
        if not self.notifier:
            return
        try:
            event = NotificationEvent(
                title=f"Agent failed: {issue.identifier}",
                message="Agent encountered an error",
                level=NotificationLevel.ERROR,
                issue_id=issue.id,
                issue_identifier=issue.identifier,
                issue_title=issue.title,
                error=error[:500],
            )
            msg_id = self._issue_notifications.pop(issue.id, None)
            if msg_id:
                await self.notifier.update_card(msg_id, event)
            else:
                await self.notifier.send_card(event)
        except Exception:
            logger.exception("Failed to send failure notification for %s", issue.identifier)
