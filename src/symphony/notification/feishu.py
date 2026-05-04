"""Feishu Bot notification provider."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

import httpx

from symphony.config import NotificationConfig
from symphony.notification.base import (
    CardAction,
    Notifier,
    NotificationEvent,
)
from symphony.notification.feishu_cards import (
    build_status_card,
    build_text_message,
    card_to_content,
)

logger = logging.getLogger(__name__)


class FeishuNotifier(Notifier):
    """Feishu Bot notification provider via IM API."""

    def __init__(self, config: NotificationConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._issue_messages: dict[str, str] = {}
        self._callback_handlers: dict[str, Callable] = {}

    @property
    def _base_url(self) -> str:
        return self.config.feishu_base_url.rstrip("/")

    def register_callback(self, action: str, handler: Callable) -> None:
        """Register a handler for a card action button."""
        self._callback_handlers[action] = handler

    def get_issue_message_id(self, issue_id: str) -> str | None:
        """Get the message ID for an issue's notification thread."""
        return self._issue_messages.get(issue_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        if not self.config.feishu_app_id or not self.config.feishu_app_secret:
            raise ValueError("Feishu notification requires feishu_app_id and feishu_app_secret")

        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)
        await self._refresh_token()
        logger.info("Feishu notifier initialized")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Auth (same pattern as tracker/feishu.py)
    # ------------------------------------------------------------------

    async def _refresh_token(self) -> None:
        if not self._client:
            raise RuntimeError("Client not initialized")

        resp = await self._client.post(
            "/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.config.feishu_app_id,
                "app_secret": self.config.feishu_app_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code", -1) != 0:
            raise RuntimeError(f"Feishu auth failed: {data.get('msg')}")

        self._token = data["tenant_access_token"]
        expire = data.get("expire", 7200)
        self._token_expires_at = time.monotonic() + expire - 300
        logger.debug("Feishu notifier token refreshed")

    async def _ensure_token(self) -> None:
        if time.monotonic() >= self._token_expires_at:
            await self._refresh_token()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._client:
            raise RuntimeError("Client not initialized")

        await self._ensure_token()
        headers = {"Authorization": f"Bearer {self._token}"}

        kwargs: dict[str, Any] = {"headers": headers}
        if params:
            kwargs["params"] = params
        if json_body:
            kwargs["content"] = json.dumps(json_body, ensure_ascii=False)
            kwargs["headers"]["Content-Type"] = "application/json; charset=utf-8"

        resp = await self._client.request(method, path, **kwargs)

        if resp.status_code == 401:
            await self._refresh_token()
            kwargs["headers"]["Authorization"] = f"Bearer {self._token}"
            resp = await self._client.request(method, path, **kwargs)

        resp.raise_for_status()
        data = resp.json()

        if data.get("code", -1) != 0:
            raise RuntimeError(f"Feishu IM API error: code={data.get('code')} msg={data.get('msg')}")

        return data.get("data", {})

    # ------------------------------------------------------------------
    # Notifier interface
    # ------------------------------------------------------------------

    def _resolve_target(self, chat_id: str | None, user_id: str | None) -> tuple[str, str]:
        """Resolve (receive_id_type, receive_id) for the API call."""
        if user_id:
            return ("open_id", user_id)
        target_chat = chat_id or self.config.feishu_chat_id
        if target_chat:
            return ("chat_id", target_chat)
        if self.config.feishu_admin_open_id:
            return ("open_id", self.config.feishu_admin_open_id)
        raise ValueError("No notification target configured (chat_id or user_id)")

    async def send(
        self,
        event: NotificationEvent,
        *,
        chat_id: str | None = None,
        user_id: str | None = None,
    ) -> str | None:
        receive_id_type, receive_id = self._resolve_target(chat_id, user_id)
        text_payload = build_text_message(event)

        data = await self._request(
            "POST",
            "/open-apis/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            json_body={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps(text_payload, ensure_ascii=False),
            },
        )

        msg_id = data.get("message_id")
        if msg_id and event.issue_id:
            self._issue_messages[event.issue_id] = msg_id
        return msg_id

    async def send_card(
        self,
        event: NotificationEvent,
        actions: list[CardAction] | None = None,
        *,
        chat_id: str | None = None,
        user_id: str | None = None,
    ) -> str | None:
        receive_id_type, receive_id = self._resolve_target(chat_id, user_id)
        card = build_status_card(event, actions)

        data = await self._request(
            "POST",
            "/open-apis/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            json_body={
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": card_to_content(card),
            },
        )

        msg_id = data.get("message_id")
        if msg_id and event.issue_id:
            self._issue_messages[event.issue_id] = msg_id
        return msg_id

    async def reply(
        self,
        message_id: str,
        event: NotificationEvent,
    ) -> str | None:
        text_payload = build_text_message(event)

        data = await self._request(
            "POST",
            f"/open-apis/im/v1/messages/{message_id}/reply",
            json_body={
                "msg_type": "text",
                "content": json.dumps(text_payload, ensure_ascii=False),
            },
        )
        return data.get("message_id")

    async def update_card(
        self,
        message_id: str,
        event: NotificationEvent,
        actions: list[CardAction] | None = None,
    ) -> bool:
        card = build_status_card(event, actions)

        try:
            await self._request(
                "PATCH",
                f"/open-apis/im/v1/messages/{message_id}",
                json_body={"content": card_to_content(card)},
            )
            return True
        except Exception as e:
            logger.error("Failed to update card %s: %s", message_id, e)
            return False

    async def handle_callback(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle interactive card action callback from Feishu webhook."""
        token = payload.get("token", "")
        if self.config.feishu_verification_token and token != self.config.feishu_verification_token:
            logger.warning("Invalid callback token")
            return {"toast": {"type": "error", "content": "Invalid token"}}

        action_value = payload.get("action", {}).get("value", {})
        action_name = action_value.get("action", "")

        handler = self._callback_handlers.get(action_name)
        if not handler:
            logger.warning("No handler for action: %s", action_name)
            return {"toast": {"type": "error", "content": f"Unknown action: {action_name}"}}

        try:
            await handler(payload)
            return {"toast": {"type": "success", "content": f"Action '{action_name}' executed"}}
        except Exception as e:
            logger.error("Callback handler failed: %s", e)
            return {"toast": {"type": "error", "content": str(e)}}
