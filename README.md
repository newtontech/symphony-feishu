# Symphony

A long-running automation service that orchestrates coding agents to get project work done.

## Overview

Symphony reads work from issue trackers (currently Linear), creates isolated workspaces, and runs coding agent sessions to complete tasks automatically.

## Features

- **Workflow-based automation**: Define workflows in Markdown with YAML front matter
- **Linear integration**: Fetch and update issues via GraphQL API
- **Isolated workspaces**: Each task runs in its own workspace
- **Agent orchestration**: JSON-RPC protocol over stdio for agent communication
- **HTTP API**: RESTful API and dashboard for monitoring
- **Retry with backoff**: Configurable retry logic with exponential backoff
- **Token accounting**: Track token usage across sessions

## Installation

```bash
# Using uv (recommended)
uv sync

# Or with pip
pip install -e .
```

## Quick Start

1. **Initialize a new project:**
   ```bash
   symphony init
   ```

2. **Set environment variables:**
   ```bash
   export SYMPHONY_TRACKER_LINEAR_API_KEY=your-api-key
   ```

3. **Validate your workflow:**
   ```bash
   symphony validate WORKFLOW.md
   ```

4. **Start the server:**
   ```bash
   symphony start
   ```

## CLI Commands

```bash
symphony start [--workflow FILE] [--port PORT]  # Start the server
symphony status                                   # Check server status
symphony validate WORKFLOW.md                     # Validate a workflow
symphony init                                     # Initialize a new project
symphony config                                   # Show configuration
```

## Configuration

Configuration is managed via environment variables with the `SYMPHONY_` prefix:

| Variable | Description | Default |
|----------|-------------|---------|
| `SYMPHONY_WORKFLOW_PATH` | Path to WORKFLOW.md | `./WORKFLOW.md` |
| `SYMPHONY_POLL_INTERVAL_SECONDS` | Polling interval | `30.0` |
| `SYMPHONY_SERVER_PORT` | HTTP server port | `8080` |
| `SYMPHONY_SERVER_HOST` | HTTP server host | `0.0.0.0` |
| `SYMPHONY_TRACKER_LINEAR_API_KEY` | Linear API key | - |
| `SYMPHONY_WORKSPACE_BASE_PATH` | Workspace directory | `./workspaces` |
| `SYMPHONY_AGENT_EXECUTABLE` | Agent executable | `codex` |

## Workflow Format

Workflows are defined in Markdown files with YAML front matter:

```markdown
---
name: my-workflow
max_concurrent: 2
retry_limit: 3
timeout_minutes: 60
labels:
  - bug
  - feature
---

# Task Instructions

Work on issue {{ issue.identifier }}: {{ issue.title }}

Your workspace: {{ workspace_path }}
```

### Required Placeholders

- `{{ issue }}` - Issue object
- `{{ workspace }}` or `{{ workspace_path }}` - Workspace path

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `name` | string | `default` | Workflow name |
| `max_concurrent` | int | `1` | Max concurrent workspaces |
| `retry_limit` | int | `3` | Number of retries |
| `retry_delay_seconds` | float | `60.0` | Initial retry delay |
| `timeout_minutes` | int | `60` | Session timeout |
| `labels` | list | `[]` | Filter by labels |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/status` | GET | Orchestrator status |
| `/api/v1/metrics` | GET | System metrics |
| `/api/v1/workspaces` | GET | List workspaces |
| `/api/v1/workflow` | GET | Get workflow config |
| `/api/v1/action` | POST | Perform action (start/stop/pause/resume) |
| `/api/v1/validate` | POST | Validate workflow |
| `/api/v1/dashboard` | GET | Dashboard data |

## Architecture

```
src/symphony/
├── main.py          # CLI entry point
├── config.py        # Configuration layer
├── models.py        # Pydantic models
├── workflow.py      # WORKFLOW.md loader
├── orchestrator.py  # Core orchestration
├── workspace.py     # Workspace manager
├── agent_runner.py  # Agent integration
├── protocol.py      # JSON-RPC protocol
├── tracker/
│   ├── base.py      # Abstract tracker interface
│   └── linear.py    # Linear GraphQL client
└── server/
    ├── app.py       # FastAPI application
    └── routes.py    # HTTP routes
```

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src/symphony

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/
```

## License

MIT
