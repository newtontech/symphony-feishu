"""Tests for workflow loader."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from symphony.models import IssuePriority, WorkflowConfig
from symphony.workflow import (
    WorkflowLoadError,
    load_workflow,
    render_prompt,
    validate_workflow,
)


def test_load_workflow_basic():
    """Test loading a basic workflow file."""
    content = """---
name: test-workflow
max_concurrent: 2
---

# Test Prompt

Work on issue {{ issue.identifier }} in {{ workspace_path }}.
"""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        path = Path(f.name)

    try:
        workflow = load_workflow(path)

        assert workflow.config.name == "test-workflow"
        assert workflow.config.max_concurrent == 2
        assert "{{ issue.identifier }}" in workflow.prompt
        assert "{{ workspace_path }}" in workflow.prompt
    finally:
        path.unlink()


def test_load_workflow_with_all_config():
    """Test loading a workflow with all configuration options."""
    content = """---
name: full-workflow
description: Full workflow test
max_concurrent: 3
retry_limit: 5
retry_delay_seconds: 120.0
timeout_minutes: 30
labels:
  - bug
  - feature
priority_filter:
  - urgent
  - high
---

# Full Workflow

Process {{ issue.title }}
"""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        path = Path(f.name)

    try:
        workflow = load_workflow(path)

        assert workflow.config.name == "full-workflow"
        assert workflow.config.description == "Full workflow test"
        assert workflow.config.max_concurrent == 3
        assert workflow.config.retry_limit == 5
        assert workflow.config.retry_delay_seconds == 120.0
        assert workflow.config.timeout_minutes == 30
        assert "bug" in workflow.config.labels
        assert "feature" in workflow.config.labels
        assert IssuePriority.URGENT in workflow.config.priority_filter
        assert IssuePriority.HIGH in workflow.config.priority_filter
    finally:
        path.unlink()


def test_load_workflow_missing_file():
    """Test error handling for missing file."""
    with pytest.raises(WorkflowLoadError, match="not found"):
        load_workflow(Path("/nonexistent/WORKFLOW.md"))


def test_load_workflow_empty_prompt():
    """Test error handling for empty prompt."""
    content = """---
name: empty
---
"""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        path = Path(f.name)

    try:
        with pytest.raises(WorkflowLoadError, match="no prompt content"):
            load_workflow(path)
    finally:
        path.unlink()


def test_validate_workflow_valid():
    """Test validation of a valid workflow."""
    content = """---
name: valid
max_concurrent: 1
retry_limit: 3
timeout_minutes: 60
---

Work on {{ issue }} in {{ workspace }}.
"""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        path = Path(f.name)

    try:
        errors = validate_workflow(path)
        assert errors == []
    finally:
        path.unlink()


def test_validate_workflow_missing_placeholders():
    """Test validation catches missing placeholders."""
    content = """---
name: invalid
---

Work on issue without placeholders.
"""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        path = Path(f.name)

    try:
        errors = validate_workflow(path)
        assert len(errors) == 2
        assert any("{{ issue }}" in e for e in errors)
        assert any("{{ workspace }}" in e for e in errors)
    finally:
        path.unlink()


def test_validate_workflow_invalid_config():
    """Test validation catches invalid configuration."""
    content = """---
name: invalid
max_concurrent: 0
retry_limit: -1
timeout_minutes: 0
---

Work on {{ issue }} in {{ workspace }}.
"""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        path = Path(f.name)

    try:
        errors = validate_workflow(path)
        assert any("max_concurrent" in e for e in errors)
        assert any("retry_limit" in e for e in errors)
        assert any("timeout_minutes" in e for e in errors)
    finally:
        path.unlink()


def test_render_prompt():
    """Test prompt rendering with context."""
    from symphony.models import Workflow

    config = WorkflowConfig(name="test")
    workflow = Workflow(
        config=config,
        prompt="Hello {{ name }}, work on {{ issue.identifier }}",
    )

    result = render_prompt(workflow, {"name": "Alice", "issue": {"identifier": "TEST-123"}})

    assert result == "Hello Alice, work on TEST-123"


def test_render_prompt_missing_variable():
    """Test prompt rendering with missing variable raises error."""
    from symphony.models import Workflow

    config = WorkflowConfig(name="test")
    workflow = Workflow(
        config=config,
        prompt="Hello {{ missing_variable }}",
    )

    with pytest.raises(Exception):  # Jinja2 UndefinedError
        render_prompt(workflow, {})
