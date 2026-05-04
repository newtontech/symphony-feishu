---
name: symphony-default
description: Default Symphony workflow for coding agents
tracker:
  kind: linear
max_concurrent: 1
retry_limit: 3
retry_delay_seconds: 60
timeout_minutes: 60
labels:
  - symphony
priority_filter:
  - urgent
  - high
  - medium
---

# Symphony Agent Task

You are working on issue **{{ issue.identifier }}**: {{ issue.title }}

## Issue Details

**Priority:** {{ issue.priority.value }}
**Status:** {{ issue.status.value }}
**Labels:** {{ issue.labels | join(', ') }}

### Description

{{ issue.description or 'No description provided.' }}

## Your Workspace

Your workspace is located at: `{{ workspace_path }}`

## Instructions

1. **Understand the Issue**: Read and analyze the issue description carefully
2. **Plan Your Approach**: Create a plan for implementing the required changes
3. **Implement Changes**: Make the necessary code changes
4. **Write Tests**: Ensure adequate test coverage for your changes
5. **Verify**: Run tests and verify everything works as expected
6. **Commit**: Create a clean, descriptive commit

## Guidelines

- Follow the project's coding standards
- Write clear, self-documenting code
- Include appropriate error handling
- Update documentation if needed

Please complete this task thoroughly and carefully.
