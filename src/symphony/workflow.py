"""WORKFLOW.md loader with YAML front matter support."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter
import yaml

from symphony.models import IssuePriority, Workflow, WorkflowConfig


class WorkflowLoadError(Exception):
    """Error loading workflow file."""

    pass


def load_workflow(path: Path) -> Workflow:
    """Load a workflow from a WORKFLOW.md file.

    Args:
        path: Path to the WORKFLOW.md file

    Returns:
        Workflow object with config and prompt

    Raises:
        WorkflowLoadError: If file cannot be loaded or parsed
    """
    if not path.exists():
        raise WorkflowLoadError(f"Workflow file not found: {path}")

    try:
        post = frontmatter.load(str(path))
    except Exception as e:
        raise WorkflowLoadError(f"Failed to parse workflow file: {e}") from e

    # Extract YAML front matter as config
    metadata = post.metadata or {}
    config = _parse_workflow_config(metadata)

    # Body is the prompt template
    prompt = post.content.strip()

    if not prompt:
        raise WorkflowLoadError(f"Workflow file has no prompt content: {path}")

    return Workflow(
        config=config,
        prompt=prompt,
        source_path=str(path.absolute()),
    )


def _parse_workflow_config(metadata: dict[str, Any]) -> WorkflowConfig:
    """Parse workflow configuration from front matter metadata.

    Args:
        metadata: Parsed YAML front matter

    Returns:
        WorkflowConfig object
    """
    # Handle priority filter conversion
    priority_filter = metadata.get("priority_filter", list(IssuePriority))
    if isinstance(priority_filter, list):
        priority_filter = [
            IssuePriority(p) if isinstance(p, str) else p
            for p in priority_filter
        ]

    return WorkflowConfig(
        name=metadata.get("name", "default"),
        description=metadata.get("description"),
        tracker_filter=metadata.get("tracker_filter", {}),
        workspace_template=metadata.get("workspace_template"),
        max_concurrent=metadata.get("max_concurrent", 1),
        retry_limit=metadata.get("retry_limit", 3),
        retry_delay_seconds=metadata.get("retry_delay_seconds", 60.0),
        timeout_minutes=metadata.get("timeout_minutes", 60),
        labels=metadata.get("labels", []),
        priority_filter=priority_filter,
    )


def validate_workflow(path: Path) -> list[str]:
    """Validate a workflow file and return any errors.

    Args:
        path: Path to the WORKFLOW.md file

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    try:
        workflow = load_workflow(path)
    except WorkflowLoadError as e:
        return [str(e)]

    # Validate config
    config = workflow.config

    if config.max_concurrent < 1:
        errors.append("max_concurrent must be at least 1")

    if config.retry_limit < 0:
        errors.append("retry_limit must be non-negative")

    if config.retry_delay_seconds < 0:
        errors.append("retry_delay_seconds must be non-negative")

    if config.timeout_minutes < 1:
        errors.append("timeout_minutes must be at least 1")

    # Validate prompt has required placeholders
    prompt = workflow.prompt
    # Jinja2 uses {{ variable }} syntax
    required_placeholders = ["{{ issue", "{{ issue}}", "{{issue", "{{issue}}"]
    has_issue = any(ph in prompt for ph in required_placeholders)
    if not has_issue:
        errors.append("Prompt missing required placeholder: {{ issue }}")

    required_workspace = ["{{ workspace", "{{ workspace}}", "{{workspace", "{{workspace}}"]
    has_workspace = any(ph in prompt for ph in required_workspace)
    if not has_workspace:
        errors.append("Prompt missing required placeholder: {{ workspace }}")

    return errors


def render_prompt(workflow: Workflow, context: dict[str, Any]) -> str:
    """Render a workflow prompt with context variables.

    Args:
        workflow: Workflow object
        context: Dictionary of variables to substitute

    Returns:
        Rendered prompt string
    """
    from jinja2 import Environment, StrictUndefined

    env = Environment(undefined=StrictUndefined)
    template = env.from_string(workflow.prompt)
    return template.render(**context)
