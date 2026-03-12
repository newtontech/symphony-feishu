"""Agent runner for executing coding agents."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from symphony.config import AgentConfig
from symphony.models import AgentSession, Issue, Workspace, Workflow
from symphony.protocol import ProtocolHandler
from symphony.workflow import render_prompt

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class AgentError(Exception):
    """Agent execution error."""

    pass


class AgentRunner:
    """Runs coding agent sessions."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self._sessions: dict[str, AgentSession] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def run(
        self,
        workspace: Workspace,
        issue: Issue,
        workflow: Workflow,
    ) -> AgentSession:
        """Run an agent session for an issue.

        Args:
            workspace: Workspace to run in
            issue: Issue to process
            workflow: Workflow configuration

        Returns:
            AgentSession with results

        Raises:
            AgentError: If agent execution fails
        """
        session_id = str(workspace.id)
        logger.info(f"Starting agent session {session_id} for issue {issue.identifier}")

        session = AgentSession(
            id=workspace.id,
            workspace_id=workspace.id,
            issue_id=issue.id,
            status="starting",
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        self._sessions[session_id] = session

        try:
            # Render the prompt
            prompt = self._render_prompt(workflow, issue, workspace)

            # Start the agent process
            process = await self._start_agent(workspace.path, prompt)
            self._processes[session_id] = process

            # Setup protocol handler
            protocol = ProtocolHandler()
            self._setup_protocol_handlers(protocol, session)

            # Start protocol
            await protocol.start(process.stdout, process.stdin)

            # Initialize
            await protocol.send_request("initialize", {
                "protocolVersion": self.config.protocol_version,
                "workspace": str(workspace.path),
                "issue": issue.model_dump(),
            })

            session.status = "running"

            # Wait for completion
            await self._wait_for_completion(process, protocol, session)

            # Get final token count
            try:
                token_result = await protocol.send_request("tokens/get")
                session.tokens_used = token_result.get("total", 0)
            except Exception:
                pass

            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"Agent session {session_id} completed")

        except asyncio.TimeoutError:
            session.status = "timeout"
            session.error = f"Session timed out after {self.config.timeout_seconds}s"
            logger.error(f"Agent session {session_id} timed out")

        except Exception as e:
            session.status = "failed"
            session.error = str(e)
            logger.error(f"Agent session {session_id} failed: {e}")
            raise AgentError(f"Agent execution failed: {e}") from e

        finally:
            # Cleanup
            if session_id in self._processes:
                process = self._processes.pop(session_id)
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        process.kill()

            await protocol.stop()

        return session

    async def _start_agent(
        self,
        workspace_path: str,
        prompt: str,
    ) -> asyncio.subprocess.Process:
        """Start the agent subprocess.

        Args:
            workspace_path: Path to workspace
            prompt: Rendered prompt

        Returns:
            Subprocess handle
        """
        logger.info(f"Starting agent: {self.config.executable}")

        # Set up environment
        env = os.environ.copy()
        env["SYMPHONY_WORKSPACE"] = workspace_path
        env["SYMPHONY_PROMPT"] = prompt

        process = await asyncio.create_subprocess_exec(
            self.config.executable,
            "--protocol",
            "--workspace",
            workspace_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_path,
            env=env,
        )

        return process

    def _render_prompt(
        self,
        workflow: Workflow,
        issue: Issue,
        workspace: Workspace,
    ) -> str:
        """Render the workflow prompt with context."""
        context: dict[str, Any] = {
            "issue": issue,
            "workspace": workspace,
            "issue_id": issue.id,
            "issue_identifier": issue.identifier,
            "issue_title": issue.title,
            "issue_description": issue.description or "",
            "issue_labels": issue.labels,
            "workspace_path": workspace.path,
        }

        return render_prompt(workflow, context)

    def _setup_protocol_handlers(
        self,
        protocol: ProtocolHandler,
        session: AgentSession,
    ) -> None:
        """Set up protocol message handlers."""

        async def handle_task_update(params: Any) -> None:
            logger.debug(f"Task update: {params}")
            # Could store task state for progress tracking

        async def handle_log(params: Any) -> None:
            level = params.get("level", "info")
            message = params.get("message", "")
            getattr(logger, level, logger.info)(f"[Agent] {message}")

        async def handle_tokens(params: Any) -> None:
            session.tokens_used = params.get("total", session.tokens_used)

        protocol.on_request("task/update", handle_task_update)
        protocol.on_request("log/message", handle_log)
        protocol.on_request("tokens/report", handle_tokens)

    async def _wait_for_completion(
        self,
        process: asyncio.subprocess.Process,
        protocol: ProtocolHandler,
        session: AgentSession,
    ) -> None:
        """Wait for agent completion."""
        timeout = self.config.timeout_seconds

        async def read_stderr() -> None:
            """Read and log stderr."""
            if process.stderr:
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    logger.warning(f"[Agent stderr] {line.decode().strip()}")

        # Start stderr reader
        stderr_task = asyncio.create_task(read_stderr())

        try:
            # Wait for process to complete
            await asyncio.wait_for(process.wait(), timeout=timeout)
        finally:
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass

        if process.returncode != 0:
            raise AgentError(f"Agent exited with code {process.returncode}")

    async def get_session(self, session_id: str) -> AgentSession | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    async def list_sessions(self) -> list[AgentSession]:
        """List all sessions."""
        return list(self._sessions.values())

    async def cancel_session(self, session_id: str) -> bool:
        """Cancel a running session.

        Args:
            session_id: Session to cancel

        Returns:
            True if cancelled, False if not found
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        process = self._processes.get(session_id)
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()

        session.status = "cancelled"
        session.error = "Session cancelled by user"
        session.completed_at = datetime.now(timezone.utc).isoformat()

        return True


def get_agent_runner(config: AgentConfig) -> AgentRunner:
    """Create an agent runner instance."""
    return AgentRunner(config)
