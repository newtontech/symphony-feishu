"""Feishu interactive card message templates."""

from __future__ import annotations

import json
from typing import Any

from symphony.notification.base import CardAction, NotificationEvent, NotificationLevel

# Feishu card header color mapping
_LEVEL_COLORS: dict[NotificationLevel, str] = {
    NotificationLevel.INFO: "blue",
    NotificationLevel.SUCCESS: "green",
    NotificationLevel.WARNING: "orange",
    NotificationLevel.ERROR: "red",
}

# Feishu button style mapping
_BUTTON_STYLES: dict[str, str] = {
    "primary": "primary",
    "danger": "danger",
    "default": "default",
}


def build_text_message(event: NotificationEvent) -> dict[str, str]:
    """Build a simple text message payload."""
    parts: list[str] = []
    if event.issue_identifier:
        parts.append(f"[{event.issue_identifier}]")
    parts.append(event.title)
    if event.message:
        parts.append(f"- {event.message}")
    return {"text": " ".join(parts)}


def build_status_card(
    event: NotificationEvent,
    actions: list[CardAction] | None = None,
) -> dict[str, Any]:
    """Build a Feishu interactive card for agent status notifications."""
    color = _LEVEL_COLORS.get(event.level, "blue")

    # Build body content lines
    body_lines: list[str] = []

    if event.issue_identifier and event.issue_title:
        body_lines.append(f"**Issue:** [{event.issue_identifier}] {event.issue_title}")

    if event.message:
        body_lines.append(f"**Status:** {event.message}")

    if event.pr_url:
        pr_text = f"[PR #{event.pr_number}]({event.pr_url})" if event.pr_number else f"[PR]({event.pr_url})"
        body_lines.append(f"**Pull Request:** {pr_text}")

    if event.workspace_path:
        body_lines.append(f"**Workspace:** `{event.workspace_path}`")

    if event.error:
        body_lines.append(f"**Error:** {event.error[:500]}")

    content_text = "\n".join(body_lines) if body_lines else event.message

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": content_text},
        }
    ]

    # Add action buttons if provided
    if actions:
        action_buttons: list[dict[str, Any]] = []
        for act in actions:
            action_buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": act.label},
                "type": _BUTTON_STYLES.get(act.style, "default"),
                "value": {"action": act.action, **act.value},
            })
        elements.append({"tag": "action", "actions": action_buttons})

    card: dict[str, Any] = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": event.title},
            "template": color,
        },
        "elements": elements,
    }

    return card


def card_to_content(card: dict[str, Any]) -> str:
    """Serialize card dict to content string for Feishu API."""
    return json.dumps(card, ensure_ascii=False)
