# Symphony Implementation Task

Implement Symphony according to the OpenAI Symphony specification.

## Overview
Symphony is a long-running automation service that orchestrates coding agents to get project work done. It reads work from Linear (issue tracker), creates isolated workspaces, and runs coding agent sessions.

## Core Components

1. **Workflow Loader** - Read WORKFLOW.md, parse YAML front matter + prompt body
2. **Config Layer** - Typed config with defaults and env vars
3. **Issue Tracker Client** - Linear GraphQL API integration
4. **Orchestrator** - Poll loop, state machine, retries
5. **Workspace Manager** - Create/isolate workspaces, run hooks
6. **Agent Runner** - Launch coding agent, implement app-server protocol
7. **HTTP Server** - Dashboard and REST API (optional)

## Tech Stack
- Python 3.11+ with uv
- FastAPI + uvicorn
- httpx for GraphQL
- Jinja2 for templates
- Pydantic v2 for models
- asyncio

## CLI Commands
- `symphony start [--workflow FILE] [--port PORT]`
- `symphony status`
- `symphony validate`

## File Structure
Create this structure:
```
src/symphony/
  __init__.py
  main.py          # CLI entry
  config.py        # Config layer
  workflow.py      # WORKFLOW.md loader
  models.py        # Pydantic models
  orchestrator.py  # Core orchestration
  workspace.py     # Workspace manager
  agent_runner.py  # Agent integration
  protocol.py      # App-server protocol
  tracker/
    __init__.py
    base.py        # Abstract interface
    linear.py      # Linear client
  server/
    __init__.py
    app.py         # FastAPI app
    routes.py      # HTTP routes
tests/
  test_workflow.py
  test_config.py
  test_orchestrator.py
```

## Key Features
- WORKFLOW.md with YAML front matter
- Linear GraphQL with pagination
- JSON-RPC protocol over stdio
- Retry with exponential backoff
- Workspace sanitization and safety
- Token accounting and metrics

## Reference
Full spec: https://github.com/openai/symphony/blob/main/SPEC.md

Please implement all components with:
- Full type hints
- Error handling
- Docstrings
- Unit tests