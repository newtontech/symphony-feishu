"""Tests for workspace manager."""

import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from symphony.config import WorkspaceConfig
from symphony.models import Issue, IssuePriority, IssueStatus, Workspace, WorkspaceState
from symphony.workspace import WorkspaceError, WorkspaceManager


@pytest.fixture
def temp_workspace_base(tmp_path):
    """Create a temporary workspace base directory."""
    base = tmp_path / "workspaces"
    base.mkdir(parents=True, exist_ok=True)
    return base


@pytest.fixture
def workspace_config(temp_workspace_base):
    """Create workspace configuration."""
    return WorkspaceConfig(
        base_path=temp_workspace_base,
        template_path=None,
        cleanup_on_success=True,
        cleanup_on_failure=False,
        pre_hooks=[],
        post_hooks=[],
    )


@pytest.fixture
def mock_issue():
    """Create a mock issue."""
    return Issue(
        id="issue-123",
        identifier="TEST-123",
        title="Test Issue",
        description="Test description",
        status=IssueStatus.TODO,
        priority=IssuePriority.MEDIUM,
        labels=["test"],
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.mark.asyncio
async def test_workspace_manager_initialize(workspace_config, temp_workspace_base):
    """Test workspace manager initialization."""
    manager = WorkspaceManager(workspace_config)
    await manager.initialize()

    assert temp_workspace_base.exists()


@pytest.mark.asyncio
async def test_workspace_manager_create(workspace_config, mock_issue):
    """Test creating a workspace."""
    manager = WorkspaceManager(workspace_config)
    await manager.initialize()

    workspace = await manager.create(mock_issue)

    assert workspace.issue_id == "issue-123"
    assert workspace.state == WorkspaceState.READY
    assert Path(workspace.path).exists()
    assert (Path(workspace.path) / "ISSUE.md").exists()


@pytest.mark.asyncio
async def test_workspace_manager_get(workspace_config, mock_issue):
    """Test getting a workspace by ID."""
    manager = WorkspaceManager(workspace_config)
    await manager.initialize()

    created = await manager.create(mock_issue)
    retrieved = await manager.get(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id


@pytest.mark.asyncio
async def test_workspace_manager_list_all(workspace_config, mock_issue):
    """Test listing all workspaces."""
    manager = WorkspaceManager(workspace_config)
    await manager.initialize()

    workspace1 = await manager.create(mock_issue)

    # Create another issue
    issue2 = Issue(
        id="issue-456",
        identifier="TEST-456",
        title="Another Issue",
        description="Another description",
        status=IssueStatus.TODO,
        priority=IssuePriority.HIGH,
        labels=["bug"],
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    workspace2 = await manager.create(issue2)

    all_workspaces = await manager.list_all()
    assert len(all_workspaces) == 2
    assert {w.id for w in all_workspaces} == {workspace1.id, workspace2.id}


@pytest.mark.asyncio
async def test_workspace_manager_cleanup_success(workspace_config, mock_issue):
    """Test cleaning up a workspace on success."""
    manager = WorkspaceManager(workspace_config)
    await manager.initialize()

    workspace = await manager.create(mock_issue)
    workspace.state = WorkspaceState.COMPLETED

    await manager.cleanup(workspace)

    assert workspace.state == WorkspaceState.CLEANED
    assert not Path(workspace.path).exists()
    assert workspace.id not in [w.id for w in await manager.list_all()]


@pytest.mark.asyncio
async def test_workspace_manager_cleanup_failure_no_delete(workspace_config, mock_issue):
    """Test cleaning up a workspace on failure (no delete)."""
    # cleanup_on_failure is False by default
    manager = WorkspaceManager(workspace_config)
    await manager.initialize()

    workspace = await manager.create(mock_issue)
    workspace.state = WorkspaceState.FAILED

    await manager.cleanup(workspace)

    # Should not delete because cleanup_on_failure=False
    assert Path(workspace.path).exists()


@pytest.mark.asyncio
async def test_workspace_manager_sanitize_path_valid(workspace_config, temp_workspace_base):
    """Test sanitizing a valid path."""
    manager = WorkspaceManager(workspace_config)
    await manager.initialize()

    valid_path = temp_workspace_base / "test" / "file.txt"
    sanitized = await manager.sanitize_path(valid_path)

    assert str(sanitized).startswith(str(temp_workspace_base.resolve()))


@pytest.mark.asyncio
async def test_workspace_manager_sanitize_path_escape(workspace_config, temp_workspace_base):
    """Test sanitizing an escaping path."""
    manager = WorkspaceManager(workspace_config)
    await manager.initialize()

    # Try to escape workspace bounds
    escaping_path = temp_workspace_base / ".." / ".." / "etc" / "passwd"

    with pytest.raises(WorkspaceError, match="escapes workspace bounds"):
        await manager.sanitize_path(escaping_path)


@pytest.mark.asyncio
async def test_workspace_manager_with_template(tmp_path, mock_issue):
    """Test creating workspace with template."""
    # Create template directory
    template_dir = tmp_path / "template"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "README.md").write_text("# Template Project")

    config = WorkspaceConfig(
        base_path=tmp_path / "workspaces",
        template_path=template_dir,
        cleanup_on_success=True,
        cleanup_on_failure=False,
        pre_hooks=[],
        post_hooks=[],
    )

    manager = WorkspaceManager(config)
    await manager.initialize()

    workspace = await manager.create(mock_issue)

    # Check template was copied
    assert (Path(workspace.path) / "README.md").exists()
    assert (Path(workspace.path) / "README.md").read_text() == "# Template Project"