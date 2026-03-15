# Feishu Tracker Specification

## Overview

This specification defines the Feishu Tracker implementation for Symphony, supporting both Feishu Bitable (多维表格) and Feishu Task (任务) systems.

## 1. Tracker Types

### 1.1 Feishu Bitable Tracker

**Advantages:**
- Highly customizable fields
- Support for workspace path, agent status, PR URL storage
- Rich filtering and sorting
- Multiple views (Kanban, Gantt, Calendar)
- Automation rules support

**Use Cases:**
- Complex workflows with custom metadata
- Agent orchestration with state tracking
- Multi-project management

### 1.2 Feishu Task Tracker

**Advantages:**
- Native mobile experience
- Built-in reminders and due dates
- Simple task management
- Deep IM integration

**Use Cases:**
- Simple task workflows
- Mobile-first users
- Quick task creation

### 1.3 Hybrid Tracker

Combines both systems:
- Bitable: Agent orchestration state
- Task: User task view (synced from Bitable)

## 2. Data Model

### 2.1 Bitable Field Schema

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| `issue_id` | Text | Yes | Symphony internal ID |
| `identifier` | Text | Yes | Human-readable ID (e.g., FEAT-123) |
| `title` | Text | Yes | Task title |
| `description` | Text | No | Task description |
| `state` | SingleSelect | Yes | Current state |
| `priority` | Number | No | 1-4 priority |
| `workspace_path` | Text | No | Workspace directory path |
| `agent_status` | SingleSelect | No | Agent execution status |
| `attempt_count` | Number | No | Retry count |
| `last_run_at` | DateTime | No | Last execution time |
| `pr_url` | URL | No | Pull request link |
| `ci_status` | SingleSelect | No | CI status |
| `assignee` | Member | No | Responsible person |
| `labels` | MultiSelect | No | Task labels |
| `created_at` | DateTime | Yes | Creation time |
| `updated_at` | DateTime | Yes | Last update time |

### 2.2 State Mapping

```python
FEISHU_STATE_MAPPING = {
    # Symphony State -> Feishu Bitable State
    IssueStatus.BACKLOG: "Backlog",
    IssueStatus.TODO: "Todo",
    IssueStatus.IN_PROGRESS: "In Progress",
    IssueStatus.IN_REVIEW: "In Review",
    IssueStatus.DONE: "Done",
    IssueStatus.CANCELED: "Cancelled",
}
```

### 2.3 Agent Status Values

```python
class AgentStatus(str, Enum):
    """Agent execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    RETRY_QUEUED = "retry_queued"
```

## 3. API Integration

### 3.1 Authentication

```python
class FeishuConfig(BaseSettings):
    """Feishu API configuration."""
    
    model_config = SettingsConfigDict(env_prefix="FEISHU_")
    
    app_id: str
    app_secret: str
    tenant_key: str | None = None  # For internal apps
    
    # Bitable configuration
    bitable_app_token: str | None = None
    bitable_table_id: str | None = None
    
    # Task configuration
    task_list_id: str | None = None
```

### 3.2 Tenant Access Token

```python
async def get_tenant_access_token(
    app_id: str,
    app_secret: str,
) -> str:
    """Get Feishu tenant access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": app_id,
                "app_secret": app_secret,
            },
        )
        data = response.json()
        if data.get("code") != 0:
            raise AuthenticationError(f"Feishu auth failed: {data}")
        return data["tenant_access_token"]
```

### 3.3 Bitable API Operations

```python
class FeishuBitableClient:
    """Feishu Bitable API client."""
    
    async def list_records(
        self,
        table_id: str,
        filter: dict | None = None,
        sort: list | None = None,
        page_size: int = 50,
    ) -> list[dict]:
        """List records from Bitable."""
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/search"
        # ...
    
    async def create_record(
        self,
        table_id: str,
        fields: dict,
    ) -> str:
        """Create a new record."""
        # ...
    
    async def update_record(
        self,
        table_id: str,
        record_id: str,
        fields: dict,
    ) -> bool:
        """Update a record."""
        # ...
    
    async def delete_record(
        self,
        table_id: str,
        record_id: str,
    ) -> bool:
        """Delete a record."""
        # ...
```

## 4. Configuration Schema

### 4.1 WORKFLOW.md Example

```yaml
---
tracker:
  kind: feishu_bitable
  
  # Authentication
  app_id: $FEISHU_APP_ID
  app_secret: $FEISHU_APP_SECRET
  
  # Bitable configuration
  app_token: Fldxxxxx
  table_id: tblxxxxx
  
  # Field mappings (optional, defaults provided)
  fields:
    issue_id: issue_id
    identifier: identifier
    title: title
    description: description
    state: status
    priority: priority
    workspace_path: workspace_path
    agent_status: agent_status
    pr_url: pr_url
  
  # State configuration
  active_states:
    - Todo
    - In Progress
    - In Review
  terminal_states:
    - Done
    - Cancelled
    - Duplicate

notification:
  enabled: true
  chat_id: oc_xxxxx
  events:
    - on_start
    - on_complete
    - on_failure
---
```

## 5. Error Handling

### 5.1 Error Codes

```python
class FeishuErrorCode(Enum):
    """Feishu API error codes."""
    INVALID_APP_ID = 10001
    INVALID_APP_SECRET = 10002
    INVALID_ACCESS_TOKEN = 10003
    TABLE_NOT_FOUND = 10101
    RECORD_NOT_FOUND = 10102
    PERMISSION_DENIED = 10201
    RATE_LIMIT_EXCEEDED = 10301
```

### 5.2 Retry Strategy

```python
RETRY_CONFIG = {
    "max_retries": 3,
    "retry_delay": 1.0,  # seconds
    "retry_multiplier": 2.0,
    "retryable_errors": [
        FeishuErrorCode.RATE_LIMIT_EXCEEDED,
        500,  # Server error
        502,  # Bad gateway
        503,  # Service unavailable
    ],
}
```

## 6. Testing Strategy

### 6.1 Unit Tests

- Token management
- Field mapping
- State transitions
- Error handling

### 6.2 Integration Tests

- Bitable API operations
- Task API operations
- IM notification delivery

### 6.3 Test Coverage Requirements

- Core tracker: 90%
- API client: 80%
- Utilities: 70%

## 7. Security Considerations

### 7.1 Token Storage

- Use environment variables
- Never log tokens
- Rotate tokens periodically

### 7.2 Permission Scopes

Required scopes for Feishu App:
- `bitable:record:read`
- `bitable:record:write`
- `task:task:read`
- `task:task:write`
- `im:message:send_as_bot`

### 7.3 Data Isolation

- Workspace paths per issue
- No cross-issue data access
- Cleanup on terminal states