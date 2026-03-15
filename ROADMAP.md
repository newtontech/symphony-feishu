# Symphony for Feishu - Project Roadmap

## Overview

Symphony for Feishu is an AI Agent orchestration platform that integrates with Feishu (Lark) Task and Bitable systems. It enables teams to manage work at a higher level instead of supervising coding agents.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Interaction Layer                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Feishu Task  │    │  Feishu IM   │    │ Feishu Doc   │  │
│  │ (Task CRUD)  │───▶│ (Notify)     │◀───│ (Reports)    │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Orchestration Control Layer                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Feishu Bitable (Multi-dimensional Table)   │  │
│  │  ┌────────┬────────┬────────┬────────┬────────────┐  │  │
│  │  │ Issue  │ State  │ Agent  │ Work-  │ PR/Proof   │  │  │
│  │  │ ID     │        │ Status │ space  │            │  │  │
│  │  ├────────┼────────┼────────┼────────┼────────────┤  │  │
│  │  │FEAT-123│In Prog │Running │/ws/123 │ PR#456     │  │  │
│  │  └────────┴────────┴────────┴────────┴────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent Execution Layer                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Workspace 1 │    │  Workspace 2 │    │  Workspace N │  │
│  │  (Codex)     │    │  (Claude)    │    │  (OpenCode)  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Feishu Bitable Tracker
- Full Symphony SPEC.md compliance
- Customizable field mapping
- Real-time status sync
- Workspace path storage
- Agent execution metadata

### 2. Feishu Task Tracker
- Native task management experience
- Mobile-friendly
- Due date and reminder integration
- Simple workflow support

### 3. Feishu IM Notification
- Interactive message cards
- Real-time progress updates
- One-click approval/rejection
- PR link preview

### 4. i18n Support
- Chinese (Simplified)
- English
- Locale-aware error messages
- User preference storage

## Development Phases

### Phase 1: Core Infrastructure (Week 1)
- [ ] Issue #1: Feishu Tracker Base Implementation
- [ ] Issue #2: Feishu Bitable Tracker Implementation
- [ ] Issue #3: Configuration System Enhancement

### Phase 2: Integration (Week 2)
- [ ] Issue #4: Feishu Task Tracker Implementation
- [ ] Issue #5: Feishu IM Notification Integration
- [ ] Issue #6: Hybrid Tracker (Bitable + Task sync)

### Phase 3: Quality & Operations (Week 3)
- [ ] Issue #7: i18n Support (Chinese/English)
- [ ] Issue #8: CI/CD Pipeline Setup
- [ ] Issue #9: Test Coverage (80%+)

### Phase 4: Documentation & Examples (Week 4)
- [ ] Issue #10: Documentation (README, API docs, Examples)
- [ ] Issue #11: Demo Workflow Templates
- [ ] Issue #12: Deployment Guide

## Technology Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI, Pydantic
- **API Client**: httpx (async)
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **CI/CD**: GitHub Actions
- **i18n**: babel, gettext

## Configuration Example

```yaml
# WORKFLOW.md
---
tracker:
  kind: feishu_bitable  # or feishu_task, or hybrid
  app_token: Fldxxxxx
  table_id: tblxxxxx
  app_id: $FEISHU_APP_ID
  app_secret: $FEISHU_APP_SECRET
  
  # Field mappings (customizable)
  fields:
    state: status
    priority: priority
    workspace_path: workspace_path
    agent_status: agent_status
    pr_url: pr_link
    
  active_states:
    - Todo
    - In Progress
  terminal_states:
    - Done
    - Cancelled

polling:
  interval_ms: 60000

workspace:
  root: /symphony_workspaces

hooks:
  after_create: |
    git clone git@github.com:org/repo.git .
    pip install -e .

notification:
  feishu_chat_id: oc_xxxxx
  on_success: true
  on_failure: true
  on_progress: true
---

# Task Execution Prompt

You are working on a task from Feishu.

**Task ID**: {{ issue.identifier }}
**Title**: {{ issue.title }}
**Description**: {{ issue.description }}

Please follow these steps:
1. Understand requirements
2. Create implementation plan
3. Write code
4. Run tests
5. Create PR
6. Update Bitable status
```

## License

Apache License 2.0 (same as original Symphony)