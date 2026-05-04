"""CLI entry point for Symphony."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import click
import uvicorn
from rich.console import Console
from rich.table import Table

from symphony import __version__
from symphony.config import Config, get_config
from symphony.models import OrchestratorState
from symphony.orchestrator import Orchestrator
from symphony.tracker.linear import LinearClient
from symphony.workflow import load_workflow, validate_workflow

console = Console()
logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


@click.group()
@click.version_option(version=__version__)
@click.option("--log-level", default="INFO", help="Logging level")
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """Symphony - Long-running automation service for coding agents."""
    setup_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["config"] = get_config()


@cli.command()
@click.option("--workflow", "-w", type=click.Path(exists=True), help="Path to WORKFLOW.md")
@click.option("--port", "-p", default=8080, help="HTTP server port")
@click.option("--host", "-h", default="0.0.0.0", help="HTTP server host")
@click.pass_context
def start(ctx: click.Context, workflow: Optional[str], port: int, host: str) -> None:
    """Start the Symphony server.

    This starts both the HTTP API server and the orchestration engine.
    """
    config: Config = ctx.obj["config"]

    # Load workflow
    workflow_path = Path(workflow) if workflow else config.workflow_path
    if not workflow_path.exists():
        console.print(f"[red]Error: Workflow file not found: {workflow_path}[/red]")
        raise SystemExit(1)

    try:
        wf = load_workflow(workflow_path)
        console.print(f"[green]Loaded workflow: {wf.config.name}[/green]")
    except Exception as e:
        console.print(f"[red]Error loading workflow: {e}[/red]")
        raise SystemExit(1)

    # Update server config
    config.server.port = port
    config.server.host = host

    # Create tracker based on configured kind
    if config.tracker.kind == "feishu":
        from symphony.tracker.feishu import FeishuClient

        tracker = FeishuClient(config.tracker)
    else:
        tracker = LinearClient(config.tracker)
    from symphony.agent_runner import AgentRunner
    from symphony.workspace import WorkspaceManager

    workspace_manager = WorkspaceManager(config.workspace)
    agent_runner = AgentRunner(config.agent)

    # Create notifier if configured
    notifier = None
    if config.notification.kind == "feishu" and config.notification.feishu_app_id:
        from symphony.notification.feishu import FeishuNotifier

        notifier = FeishuNotifier(config.notification)

        # Register approval/reject callbacks
        if config.notification.interactive_approval:
            from symphony.models import IssueStatus

            async def handle_approve(payload: dict) -> None:
                issue_id = payload.get("action", {}).get("value", {}).get("issue_id")
                if issue_id:
                    await tracker.update_status(issue_id, IssueStatus.DONE)

            async def handle_reject(payload: dict) -> None:
                issue_id = payload.get("action", {}).get("value", {}).get("issue_id")
                if issue_id:
                    await tracker.update_status(issue_id, IssueStatus.TODO)

            notifier.register_callback("approve", handle_approve)
            notifier.register_callback("reject", handle_reject)

    # Create orchestrator
    orchestrator = Orchestrator(
        config=config,
        workflow=wf,
        tracker=tracker,
        workspace_manager=workspace_manager,
        agent_runner=agent_runner,
        notifier=notifier,
    )

    # Create app
    from symphony.server.app import create_app
    app = create_app(config=config, orchestrator=orchestrator, notifier=notifier)

    console.print(f"[green]Starting Symphony server on {host}:{port}[/green]")
    console.print(f"[blue]Dashboard: http://{host}:{port}/api/v1/dashboard[/blue]")

    # Run server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=config.logging.level.lower(),
    )


@cli.command()
@click.option("--workflow", "-w", type=click.Path(exists=True), help="Path to WORKFLOW.md")
@click.pass_context
def status(ctx: click.Context, workflow: Optional[str]) -> None:
    """Check the status of a running Symphony instance."""
    import httpx

    config: Config = ctx.obj["config"]

    try:
        response = httpx.get(
            f"http://{config.server.host}:{config.server.port}/api/v1/status",
            timeout=5.0,
        )
        response.raise_for_status()
        data = response.json()

        table = Table(title="Symphony Status")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("State", data["state"])
        table.add_row("Active Workspaces", str(data["active_workspaces"]))
        table.add_row("Total Completed", str(data["total_completed"]))
        table.add_row("Total Failed", str(data["total_failed"]))
        table.add_row("Uptime (seconds)", f"{data['uptime_seconds']:.1f}")
        table.add_row("Workflow", data.get("workflow", "N/A"))

        console.print(table)

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Symphony server[/red]")
        console.print(f"[yellow]Is the server running on {config.server.host}:{config.server.port}?[/yellow]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)


@cli.command()
@click.argument("workflow_path", type=click.Path(exists=True))
def validate(workflow_path: str) -> None:
    """Validate a WORKFLOW.md file.

    Checks syntax, configuration, and required placeholders.
    """
    path = Path(workflow_path)
    console.print(f"[blue]Validating workflow: {path}[/blue]")

    errors = validate_workflow(path)

    if errors:
        console.print("[red]Validation failed:[/red]")
        for error in errors:
            console.print(f"  [red]✗[/red] {error}")
        raise SystemExit(1)
    else:
        console.print("[green]✓ Workflow is valid[/green]")

        # Show workflow info
        wf = load_workflow(path)
        console.print(f"\n[cyan]Name:[/cyan] {wf.config.name}")
        console.print(f"[cyan]Max Concurrent:[/cyan] {wf.config.max_concurrent}")
        console.print(f"[cyan]Retry Limit:[/cyan] {wf.config.retry_limit}")
        console.print(f"[cyan]Timeout:[/cyan] {wf.config.timeout_minutes} minutes")


@cli.command()
@click.pass_context
def config_cmd(ctx: click.Context) -> None:
    """Show current configuration."""
    config: Config = ctx.obj["config"]

    console.print("[cyan]Symphony Configuration[/cyan]\n")

    table = Table()
    table.add_column("Setting", style="yellow")
    table.add_column("Value", style="white")

    table.add_row("Workflow Path", str(config.workflow_path))
    table.add_row("State Path", str(config.state_path))
    table.add_row("Poll Interval", f"{config.poll_interval_seconds}s")

    table.add_section()
    table.add_row("Server Host", config.server.host)
    table.add_row("Server Port", str(config.server.port))

    table.add_section()
    table.add_row("Workspace Base", str(config.workspace.base_path))
    table.add_row("Max Workspaces", str(config.workspace.max_workspaces))

    table.add_section()
    table.add_row("Agent Executable", config.agent.executable)
    table.add_row("Agent Timeout", f"{config.agent.timeout_seconds}s")

    console.print(table)


@cli.command()
def init() -> None:
    """Initialize a new Symphony project.

    Creates a sample WORKFLOW.md and configuration.
    """
    workflow_path = Path("WORKFLOW.md")

    if workflow_path.exists():
        console.print("[red]WORKFLOW.md already exists[/red]")
        raise SystemExit(1)

    sample_workflow = '''---
name: example-workflow
description: Example Symphony workflow
tracker:
  kind: linear  # or "feishu" for Feishu Task integration
max_concurrent: 1
retry_limit: 3
timeout_minutes: 60
labels:
  - symphony
---

# Example Workflow

You are working on issue {{ issue.identifier }}: {{ issue.title }}

## Issue Description

{{ issue.description }}

## Your Task

1. Read and understand the issue
2. Implement the required changes
3. Write tests for your changes
4. Create a clean commit

## Workspace

Your workspace is at: {{ workspace_path }}

Please complete this task carefully and thoroughly.
'''

    workflow_path.write_text(sample_workflow)
    console.print(f"[green]Created {workflow_path}[/green]")
    console.print("\n[cyan]Next steps:[/cyan]")
    console.print("1. Edit WORKFLOW.md to customize your workflow")
    console.print("2. Set tracker environment variables:")
    console.print("   Linear: SYMPHONY_TRACKER_LINEAR_API_KEY")
    console.print("   Feishu: SYMPHONY_TRACKER_FEISHU_APP_ID, SYMPHONY_TRACKER_FEISHU_APP_SECRET")
    console.print("3. Run: symphony start")


if __name__ == "__main__":
    cli()
