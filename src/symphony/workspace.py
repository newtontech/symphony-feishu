"""Workspace manager for isolated agent execution environments."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from symphony.config import WorkspaceConfig
from symphony.models import Issue, Workspace, WorkspaceState

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class WorkspaceError(Exception):
    """Workspace management error."""

    pass


class WorkspaceManager:
    """Manages isolated workspaces for agent execution."""

    def __init__(self, config: WorkspaceConfig):
        self.config = config
        self._workspaces: dict[UUID, Workspace] = {}

    async def initialize(self) -> None:
        """Initialize the workspace manager."""
        # Ensure base path exists
        self.config.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workspace manager initialized at {self.config.base_path}")

    async def create(self, issue: Issue) -> Workspace:
        """Create a new isolated workspace for an issue.

        Args:
            issue: The issue to create a workspace for

        Returns:
            Created workspace

        Raises:
            WorkspaceError: If workspace creation fails
        """
        workspace_id = uuid4()
        workspace_path = self.config.base_path / str(workspace_id)

        logger.info(f"Creating workspace {workspace_id} for issue {issue.identifier}")

        try:
            # Create workspace directory
            workspace_path.mkdir(parents=True, exist_ok=True)

            # Copy template if specified
            if self.config.template_path and self.config.template_path.exists():
                await self._copy_template(workspace_path)
            else:
                # Create basic structure
                await self._create_basic_structure(workspace_path, issue)

            # Run pre-hooks
            await self._run_hooks(
                self.config.pre_hooks,
                workspace_path,
                {"issue": issue, "workspace_id": str(workspace_id)},
            )

            # Create workspace record
            workspace = Workspace(
                id=workspace_id,
                issue_id=issue.id,
                path=str(workspace_path),
                state=WorkspaceState.READY,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

            self._workspaces[workspace_id] = workspace
            return workspace

        except Exception as e:
            # Cleanup on failure
            if workspace_path.exists():
                shutil.rmtree(workspace_path, ignore_errors=True)
            raise WorkspaceError(f"Failed to create workspace: {e}") from e

    async def cleanup(self, workspace: Workspace) -> None:
        """Clean up a workspace.

        Args:
            workspace: Workspace to clean up
        """
        if workspace.id not in self._workspaces:
            return

        workspace_path = Path(workspace.path)

        # Run post-hooks before cleanup
        try:
            await self._run_hooks(
                self.config.post_hooks,
                workspace_path,
                {"workspace": workspace},
            )
        except Exception as e:
            logger.warning(f"Post-hooks failed for workspace {workspace.id}: {e}")

        # Determine if we should delete the workspace
        should_delete = (
            (workspace.state == WorkspaceState.COMPLETED and self.config.cleanup_on_success)
            or (workspace.state == WorkspaceState.FAILED and self.config.cleanup_on_failure)
        )

        if should_delete and workspace_path.exists():
            try:
                shutil.rmtree(workspace_path)
                workspace.state = WorkspaceState.CLEANED
                logger.info(f"Cleaned up workspace {workspace.id}")
            except Exception as e:
                logger.error(f"Failed to cleanup workspace {workspace.id}: {e}")

        del self._workspaces[workspace.id]

    async def get(self, workspace_id: UUID) -> Workspace | None:
        """Get a workspace by ID."""
        return self._workspaces.get(workspace_id)

    async def list_all(self) -> list[Workspace]:
        """List all workspaces."""
        return list(self._workspaces.values())

    async def sanitize_path(self, path: Path) -> Path:
        """Sanitize a path to ensure it's within workspace bounds.

        Args:
            path: Path to sanitize

        Returns:
            Resolved path

        Raises:
            WorkspaceError: If path escapes workspace bounds
        """
        try:
            resolved = path.resolve()
            base = self.config.base_path.resolve()

            if not str(resolved).startswith(str(base)):
                raise WorkspaceError(f"Path escapes workspace bounds: {path}")

            return resolved
        except OSError as e:
            raise WorkspaceError(f"Invalid path: {path}") from e

    async def _copy_template(self, dest: Path) -> None:
        """Copy template to workspace."""
        if not self.config.template_path:
            return

        logger.info(f"Copying template from {self.config.template_path}")

        # Run copy in executor to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: shutil.copytree(
                self.config.template_path, dest, dirs_exist_ok=True
            ),
        )

    async def _create_basic_structure(self, path: Path, issue: Issue) -> None:
        """Create basic workspace structure."""
        # Create ISSUE.md file
        issue_file = path / "ISSUE.md"
        issue_content = f"""# {issue.identifier}: {issue.title}

**Status:** {issue.status.value}
**Priority:** {issue.priority.value}
**Created:** {issue.created_at}

## Description

{issue.description or 'No description provided.'}

## Labels

{', '.join(issue.labels) if issue.labels else 'None'}
"""
        issue_file.write_text(issue_content)

        # Create .workspace metadata
        workspace_meta = path / ".workspace"
        workspace_meta.write_text(
            f"""workspace_id: {uuid4()}
issue_id: {issue.id}
issue_identifier: {issue.identifier}
created_at: {datetime.now(timezone.utc).isoformat()}
"""
        )

    async def _run_hooks(
        self,
        hooks: list[str],
        workspace_path: Path,
        context: dict,
    ) -> None:
        """Run workspace hooks."""
        for hook in hooks:
            try:
                await self._run_hook(hook, workspace_path, context)
            except Exception as e:
                logger.error(f"Hook failed: {hook} - {e}")
                raise

    async def _run_hook(
        self,
        hook: str,
        workspace_path: Path,
        context: dict,
    ) -> None:
        """Run a single hook command."""
        logger.info(f"Running hook: {hook}")

        # Substitute context variables
        command = hook.format(
            workspace=str(workspace_path),
            issue_id=context.get("issue", {}).get("id", ""),
            **{k: str(v) for k, v in context.items()},
        )

        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workspace_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise WorkspaceError(
                f"Hook failed with code {process.returncode}: {stderr.decode()}"
            )

        logger.debug(f"Hook output: {stdout.decode()}")


def get_workspace_manager(config: WorkspaceConfig) -> WorkspaceManager:
    """Create a workspace manager instance."""
    return WorkspaceManager(config)
