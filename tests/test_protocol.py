"""Tests for protocol handler."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from symphony.models import JSONRPCRequest, JSONRPCResponse
from symphony.protocol import ProtocolError, ProtocolHandler


@pytest.fixture
def protocol():
    """Create a protocol handler."""
    return ProtocolHandler()


def test_protocol_handler_init(protocol):
    """Test protocol handler initialization."""
    assert protocol._request_handlers == {}
    assert protocol._response_handlers == {}
    assert protocol._next_id == 0
    assert protocol._running is False


def test_on_request(protocol):
    """Test registering request handler."""
    async def handler(params):
        return {"result": "ok"}

    protocol.on_request("test_method", handler)

    assert "test_method" in protocol._request_handlers
    assert protocol._request_handlers["test_method"] == handler


@pytest.mark.asyncio
async def test_send_request():
    """Test sending a request."""
    protocol = ProtocolHandler()

    # Create mock writer
    writer = MagicMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()

    protocol._writer = writer
    protocol._running = True

    # Create a future for the response
    response_data = {"jsonrpc": "2.0", "id": 0, "result": {"status": "ok"}}

    # Start send_request in a task
    task = asyncio.create_task(protocol.send_request("test_method", {"key": "value"}))

    # Wait a bit for the request to be sent
    await asyncio.sleep(0.01)

    # Simulate response
    future = protocol._response_handlers.get(0)
    if future:
        future.set_result({"status": "ok"})

    result = await task

    # Verify request was sent
    assert writer.write.called
    sent_data = json.loads(writer.write.call_args[0][0].decode())
    assert sent_data["jsonrpc"] == "2.0"
    assert sent_data["method"] == "test_method"
    assert sent_data["params"] == {"key": "value"}
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_send_notification():
    """Test sending a notification (no id)."""
    protocol = ProtocolHandler()

    # Create mock writer
    writer = MagicMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()

    protocol._writer = writer
    protocol._running = True

    await protocol.send_notification("test_notification", {"data": "value"})

    assert writer.write.called
    sent_data = json.loads(writer.write.call_args[0][0].decode())
    assert sent_data["jsonrpc"] == "2.0"
    assert sent_data["method"] == "test_notification"
    assert sent_data["params"] == {"data": "value"}
    assert sent_data.get("id") is None


@pytest.mark.asyncio
async def test_handle_request_dict(protocol):
    """Test handling an incoming request with dict data."""
    handled = []

    async def handler(params):
        handled.append(params)
        return {"processed": True}

    protocol.on_request("process", handler)

    # Use dict instead of Pydantic model
    data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "process",
        "params": {"input": "data"},
    }

    # _handle_request doesn't return, it sends response via _send_response
    # So we need to mock _send_response
    protocol._send_response = AsyncMock()

    await protocol._handle_request(data)

    assert len(handled) == 1
    assert handled[0] == {"input": "data"}
    protocol._send_response.assert_called_once()


@pytest.mark.asyncio
async def test_handle_request_no_handler(protocol):
    """Test handling request with no registered handler."""
    protocol._send_error = AsyncMock()

    data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "unknown_method",
        "params": {},
    }

    await protocol._handle_request(data)

    protocol._send_error.assert_called_once()
    args = protocol._send_error.call_args[0]
    assert args[0] == 1  # request_id
    assert args[1] == -32601  # error code for method not found


@pytest.mark.asyncio
async def test_handle_response_dict(protocol):
    """Test handling an incoming response with dict data."""
    # Create a future for a pending request
    future = asyncio.Future()
    protocol._response_handlers[1] = future

    data = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"status": "completed"},
    }

    await protocol._handle_response(data)

    assert future.done()
    assert future.result() == {"status": "completed"}


@pytest.mark.asyncio
async def test_handle_response_error_dict(protocol):
    """Test handling a response with error."""
    future = asyncio.Future()
    protocol._response_handlers[2] = future

    data = {
        "jsonrpc": "2.0",
        "id": 2,
        "error": {"code": -1, "message": "Something went wrong"},
    }

    await protocol._handle_response(data)

    assert future.done()
    with pytest.raises(ProtocolError):
        future.result()


@pytest.mark.asyncio
async def test_handle_notification_dict(protocol):
    """Test handling a notification (no id)."""
    called = []

    async def handler(params):
        called.append(params)

    protocol.on_request("notify", handler)

    # Notification has no id
    data = {
        "jsonrpc": "2.0",
        "id": None,
        "method": "notify",
        "params": {"event": "test"},
    }

    await protocol._handle_request(data)

    # Notifications should call handler but not send response
    assert len(called) == 1
    assert called[0] == {"event": "test"}


@pytest.mark.asyncio
async def test_send_request_not_started():
    """Test send_request when protocol not started."""
    protocol = ProtocolHandler()

    with pytest.raises(ProtocolError, match="not started"):
        await protocol.send_request("test", {})


@pytest.mark.asyncio
async def test_send_notification_not_started():
    """Test send_notification when protocol not started."""
    protocol = ProtocolHandler()

    with pytest.raises(ProtocolError, match="not started"):
        await protocol.send_notification("test", {})


@pytest.mark.asyncio
async def test_stop():
    """Test stopping the protocol handler."""
    protocol = ProtocolHandler()

    # Create mock writer
    writer = MagicMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()

    protocol._writer = writer
    protocol._running = True

    await protocol.stop()

    assert protocol._running is False
    assert writer.close.called
    assert writer.wait_closed.called