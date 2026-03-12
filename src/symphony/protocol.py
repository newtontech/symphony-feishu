"""App-server protocol implementation (JSON-RPC over stdio)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from symphony.models import JSONRPCRequest, JSONRPCResponse

logger = logging.getLogger(__name__)


class ProtocolError(Exception):
    """Protocol communication error."""

    pass


class ProtocolHandler:
    """Handles JSON-RPC protocol communication over stdio."""

    def __init__(self) -> None:
        self._request_handlers: dict[str, Callable] = {}
        self._response_handlers: dict[int | str, asyncio.Future] = {}
        self._next_id = 0
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._running = False

    def on_request(self, method: str, handler: Callable) -> None:
        """Register a handler for incoming requests.

        Args:
            method: Method name to handle
            handler: Async function to handle the request
        """
        self._request_handlers[method] = handler

    async def start(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Start the protocol handler.

        Args:
            reader: Stream reader for incoming messages
            writer: Stream writer for outgoing messages
        """
        self._reader = reader
        self._writer = writer
        self._running = True

        # Start message loop
        asyncio.create_task(self._message_loop())

    async def stop(self) -> None:
        """Stop the protocol handler."""
        self._running = False
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

    async def send_request(
        self,
        method: str,
        params: dict[str, Any] | list[Any] | None = None,
    ) -> Any:
        """Send a request and wait for response.

        Args:
            method: Method name
            params: Request parameters

        Returns:
            Response result

        Raises:
            ProtocolError: If request fails
        """
        if not self._writer:
            raise ProtocolError("Protocol not started")

        request_id = self._next_id
        self._next_id += 1

        request = JSONRPCRequest(
            id=request_id,
            method=method,
            params=params,
        )

        # Create future for response
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._response_handlers[request_id] = future

        # Send request
        message = request.model_dump_json() + "\n"
        self._writer.write(message.encode())
        await self._writer.drain()

        # Wait for response
        try:
            return await asyncio.wait_for(future, timeout=300.0)
        except asyncio.TimeoutError:
            del self._response_handlers[request_id]
            raise ProtocolError(f"Request {method} timed out")

    async def send_notification(
        self,
        method: str,
        params: dict[str, Any] | list[Any] | None = None,
    ) -> None:
        """Send a notification (no response expected).

        Args:
            method: Method name
            params: Notification parameters
        """
        if not self._writer:
            raise ProtocolError("Protocol not started")

        notification = JSONRPCRequest(
            id=None,  # No ID for notifications
            method=method,
            params=params,
        )

        message = notification.model_dump_json() + "\n"
        self._writer.write(message.encode())
        await self._writer.drain()

    async def _message_loop(self) -> None:
        """Main message processing loop."""
        if not self._reader:
            return

        buffer = ""

        while self._running:
            try:
                data = await self._reader.read(4096)
                if not data:
                    logger.info("Connection closed by peer")
                    break

                buffer += data.decode()

                # Process complete messages
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        await self._handle_message(line)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message loop: {e}")

    async def _handle_message(self, line: str) -> None:
        """Handle a single message line."""
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON message: {e}")
            return

        try:
            if "method" in data:
                # This is a request or notification
                await self._handle_request(data)
            elif "id" in data:
                # This is a response
                await self._handle_response(data)
            else:
                logger.warning(f"Unknown message format: {data}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def _handle_request(self, data: dict[str, Any]) -> None:
        """Handle an incoming request."""
        method = data.get("method")
        params = data.get("params")
        request_id = data.get("id")

        handler = self._request_handlers.get(method)
        if not handler:
            if request_id is not None:
                await self._send_error(
                    request_id,
                    -32601,
                    f"Method not found: {method}",
                )
            return

        try:
            result = await handler(params)

            # Send response if this was a request (not a notification)
            if request_id is not None:
                await self._send_response(request_id, result)

        except Exception as e:
            if request_id is not None:
                await self._send_error(request_id, -32603, str(e))

    async def _handle_response(self, data: dict[str, Any]) -> None:
        """Handle an incoming response."""
        response_id = data.get("id")
        future = self._response_handlers.pop(response_id, None)

        if not future or future.done():
            logger.warning(f"Received response for unknown request: {response_id}")
            return

        if "error" in data:
            future.set_exception(ProtocolError(data["error"]))
        else:
            future.set_result(data.get("result"))

    async def _send_response(
        self,
        request_id: int | str,
        result: Any,
    ) -> None:
        """Send a successful response."""
        if not self._writer:
            return

        response = JSONRPCResponse(
            id=request_id,
            result=result,
        )

        message = response.model_dump_json() + "\n"
        self._writer.write(message.encode())
        await self._writer.drain()

    async def _send_error(
        self,
        request_id: int | str,
        code: int,
        message: str,
        data: Any = None,
    ) -> None:
        """Send an error response."""
        if not self._writer:
            return

        response = JSONRPCResponse(
            id=request_id,
            error={"code": code, "message": message, "data": data},
        )

        msg = response.model_dump_json() + "\n"
        self._writer.write(msg.encode())
        await self._writer.drain()


# Standard protocol methods
METHODS = {
    "initialize": "Initialize the protocol connection",
    "shutdown": "Gracefully shutdown",
    "task/update": "Update task status",
    "task/complete": "Mark task as complete",
    "tokens/report": "Report token usage",
    "log/message": "Send a log message",
    "file/read": "Read a file",
    "file/write": "Write a file",
    "git/status": "Get git status",
    "git/commit": "Create a git commit",
}
