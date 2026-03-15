# Symphony for Feishu 🎼

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/newtontech/symphony-feishu/actions/workflows/ci.yml/badge.svg)](https://github.com/newtontech/symphony-feishu/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/newtontech/symphony-feishu/branch/main/graph/badge.svg)](https://codecov.io/gh/newtontech/symphony-feishu)

> **Symphony for Feishu** - AI Agent orchestration platform with Feishu (Lark) Task & Bitable integration

A long-running automation service that orchestrates coding agents to get project work done, with native Feishu integration.

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## 🚀 Features

### Feishu Integration
- **Feishu Bitable Tracker** - Multi-dimensional table with customizable fields for agent orchestration
- **Feishu Task Tracker** - Native task management with mobile support
- **Hybrid Tracker** - Combined Bitable + Task for best of both worlds
- **IM Notifications** - Interactive message cards with real-time progress updates

### Core Capabilities
- **WORKFLOW.md driven** - Version-controlled workflow configuration
- **Isolated workspaces** - Each task runs in its own directory
- **Agent orchestration** - JSON-RPC protocol for Codex, Claude, OpenCode
- **Auto-retry** - Exponential backoff with configurable limits
- **i18n support** - Chinese and English localizations

## 📦 Installation

```bash
# Using uv (recommended)
uv sync

# Or with pip
pip install symphony-feishu
```

## 🏃 Quick Start

### 1. Create Feishu App

1. Go to [Feishu Open Platform](https://open.feishu.cn/)
2. Create a new app and get `App ID` and `App Secret`
3. Enable required permissions:
   - `bitable:record:read` / `bitable:record:write`
   - `task:task:read` / `task:task:write`
   - `im:message:send_as_bot`

### 2. Create Bitable

Create a multi-dimensional table with these fields:

| Field Name | Type | Description |
|------------|------|-------------|
| issue_id | Text | Internal ID |
| identifier | Text | FEAT-123 |
| title | Text | Task title |
| status | SingleSelect | Todo/In Progress/Done |
| priority | Number | 1-4 |
| workspace_path | Text | Workspace directory |
| agent_status | SingleSelect | pending/running/succeeded/failed |

### 3. Configure Workflow

Create `WORKFLOW.md`:

```yaml
---
tracker:
  kind: feishu_bitable
  app_id: $FEISHU_APP_ID
  app_secret: $FEISHU_APP_SECRET
  app_token: Fldxxxxx
  table_id: tblxxxxx
  
  active_states:
    - Todo
    - In Progress
  terminal_states:
    - Done
    - Cancelled

notification:
  enabled: true
  chat_id: oc_xxxxx
  events:
    - on_start
    - on_complete
    - on_failure
---

# Task Execution Prompt

You are working on task {{ issue.identifier }}: {{ issue.title }}

Workspace: {{ workspace_path }}

Please:
1. Understand requirements
2. Create implementation plan
3. Write code with tests
4. Create PR
5. Update status in Bitable
```

### 4. Start Symphony

```bash
export FEISHU_APP_ID=your_app_id
export FEISHU_APP_SECRET=your_app_secret

symphony start
```

## ⚙️ Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `FEISHU_APP_ID` | Feishu App ID | - |
| `FEISHU_APP_SECRET` | Feishu App Secret | - |
| `SYMPHONY_POLL_INTERVAL_SECONDS` | Polling interval | `30.0` |
| `SYMPHONY_WORKSPACE_BASE_PATH` | Workspace directory | `./workspaces` |

## 🌐 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/status` | GET | Orchestrator status |
| `/api/v1/workspaces` | GET | List workspaces |
| `/api/v1/metrics` | GET | System metrics |

## 🏗️ Architecture

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

## 🔧 Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src/symphony --cov-fail-under=80

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/
uv run ruff format src/
```

---

<a name="中文"></a>
## 🚀 特性

### 飞书集成
- **飞书多维表格 Tracker** - 支持自定义字段的 AI 编排工作台
- **飞书任务 Tracker** - 原生任务管理，移动端友好
- **混合 Tracker** - 多维表格 + 任务系统双同步
- **IM 通知** - 交互式消息卡片，实时进度更新

### 核心能力
- **WORKFLOW.md 驱动** - 工作流配置版本控制
- **隔离工作空间** - 每个任务独立目录
- **Agent 编排** - 支持 Codex、Claude、OpenCode
- **自动重试** - 指数退避，可配置重试次数
- **国际化支持** - 中英文双语

## 📦 安装

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install symphony-feishu
```

## 🏃 快速开始

### 1. 创建飞书应用

1. 访问[飞书开放平台](https://open.feishu.cn/)
2. 创建应用并获取 `App ID` 和 `App Secret`
3. 开通权限：
   - `bitable:record:read` / `bitable:record:write`
   - `task:task:read` / `task:task:write`
   - `im:message:send_as_bot`

### 2. 创建多维表格

创建包含以下字段的多维表格：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| issue_id | 文本 | 内部 ID |
| identifier | 文本 | FEAT-123 |
| title | 文本 | 任务标题 |
| status | 单选 | 待办/进行中/已完成 |
| priority | 数字 | 1-4 |
| workspace_path | 文本 | 工作空间目录 |
| agent_status | 单选 | pending/running/succeeded/failed |

### 3. 配置工作流

创建 `WORKFLOW.md`：

```yaml
---
tracker:
  kind: feishu_bitable
  app_id: $FEISHU_APP_ID
  app_secret: $FEISHU_APP_SECRET
  app_token: Fldxxxxx
  table_id: tblxxxxx
  
  active_states:
    - 待办
    - 进行中
  terminal_states:
    - 已完成
    - 已取消

notification:
  enabled: true
  chat_id: oc_xxxxx
  events:
    - on_start
    - on_complete
    - on_failure
---

# 任务执行提示词

你正在处理任务 {{ issue.identifier }}：{{ issue.title }}

工作空间：{{ workspace_path }}

请：
1. 理解需求
2. 创建实现方案
3. 编写代码和测试
4. 创建 PR
5. 更新多维表格状态
```

### 4. 启动 Symphony

```bash
export FEISHU_APP_ID=your_app_id
export FEISHU_APP_SECRET=your_app_secret

symphony start
```

## 🛠️ 开发路线图

- [x] 项目初始化
- [ ] 飞书 Tracker 基类实现 (#1)
- [ ] 多维表格 Tracker 实现 (#2)
- [ ] 任务系统 Tracker 实现 (#3)
- [ ] IM 通知集成 (#4)
- [ ] i18n 国际化支持 (#5)
- [ ] CI/CD 流水线 (#6)
- [ ] 文档和示例 (#7)

## 📄 许可证

[Apache License 2.0](LICENSE) - 与原 Symphony 保持一致

## 🙏 致谢

- [OpenAI Symphony](https://github.com/openai/symphony) - 原始项目
- 飞书开放平台 - API 支持