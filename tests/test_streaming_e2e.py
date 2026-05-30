"""End-to-end integration test for streaming notifications.

Starts a real Python RPC server, mocks the LLM to stream tokens,
connects as a client, and verifies that chat.streaming notifications
arrive token-by-token BEFORE the final JSON-RPC response.
"""
import asyncio
import json
import os
import sys
import tempfile

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_agent():
    """Create a mock AgentLoop that simulates streaming."""
    agent = MagicMock()

    mock_result = MagicMock()
    mock_result.result = "Hello world"
    mock_result.steps = []
    mock_result.skill_created = None
    mock_result.actions_taken = []
    mock_result.scheduled_job_id = None
    mock_result.schedule_cron = None
    mock_result.iterations = 0
    mock_result.strategy_used = "conversational"

    async def fake_run(task):
        if agent.on_streaming_text:
            for ch in "Hello world":
                agent.on_streaming_text(ch, "responding")
        return mock_result

    agent.run = fake_run
    agent.on_step = None
    agent.on_streaming_text = None
    return agent


@pytest.mark.asyncio
async def test_streaming_notifications_arrive_before_response():
    """Verify chat.streaming notifications arrive token-by-token before the result."""
    from sediman.rpc_server import handle_connection

    sock_path = tempfile.mktemp(suffix=".sock")

    server = await asyncio.start_unix_server(handle_connection, path=sock_path)

    mock_agent = _make_mock_agent()

    client_reader = None
    client_writer = None

    async def run_test():
        nonlocal client_reader, client_writer
        await asyncio.sleep(0.05)
        client_reader, client_writer = await asyncio.open_unix_connection(sock_path)

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "agent.run",
            "params": {"task": "say hello"},
        }) + "\n"
        client_writer.write(request.encode())
        await client_writer.drain()

    lines = []
    streaming_order = []
    result_order = None

    async def read_responses():
        nonlocal result_order
        order = 0
        while True:
            try:
                line = await asyncio.wait_for(client_reader.readline(), timeout=5.0)
                if not line:
                    break
                msg = json.loads(line)
                lines.append(msg)
                if msg.get("method") == "chat.streaming":
                    streaming_order.append(order)
                if "result" in msg and "id" in msg:
                    result_order = order
                order += 1
            except asyncio.TimeoutError:
                break

    with patch("sediman.rpc_server._get_agent_loop", new_callable=AsyncMock, return_value=mock_agent), \
         patch("sediman.rpc_server.InterruptSignal") as mock_interrupt:
        mock_interrupt.get.return_value = MagicMock()
        mock_interrupt.get.return_value.is_set.return_value = False
        mock_interrupt.get.return_value.clear = MagicMock()

        test_task = asyncio.create_task(run_test())
        await asyncio.sleep(0.1)
        await read_responses()
        await test_task

    if client_writer:
        client_writer.close()
    server.close()
    try:
        os.unlink(sock_path)
    except Exception:
        pass

    streaming_msgs = [l for l in lines if l.get("method") == "chat.streaming"]
    result_msgs = [l for l in lines if "result" in l and "id" in l]

    print(f"\nTotal messages: {len(lines)}")
    print(f"Streaming notifications: {len(streaming_msgs)}")
    print(f"Result messages: {len(result_msgs)}")
    for i, l in enumerate(lines[:5]):
        print(f"  [{i}] {json.dumps(l)[:120]}")
    if len(lines) > 5:
        print(f"  ... ({len(lines) - 5} more)")

    assert len(streaming_msgs) > 0, f"Expected streaming notifications but got none. Messages: {lines}"
    assert len(result_msgs) > 0, f"Expected result message but got none. Messages: {lines}"
    assert result_order is not None, "Result message not found"
    assert all(s < result_order for s in streaming_order), (
        f"Streaming notifications must arrive BEFORE result. "
        f"Streaming at: {streaming_order[:5]}..., Result at: {result_order}"
    )

    tokens = "".join(m.get("params", {}).get("token", "") for m in streaming_msgs)
    assert "Hello" in tokens, f"Expected 'Hello' in streamed tokens, got: {tokens!r}"


@pytest.mark.asyncio
async def test_streaming_notifications_content():
    """Verify streaming notifications contain correct token and phase."""
    from sediman.rpc_server import handle_connection

    sock_path = tempfile.mktemp(suffix=".sock")
    server = await asyncio.start_unix_server(handle_connection, path=sock_path)

    mock_agent = _make_mock_agent()

    client_reader = None
    client_writer = None

    async def run_test():
        nonlocal client_reader, client_writer
        await asyncio.sleep(0.05)
        client_reader, client_writer = await asyncio.open_unix_connection(sock_path)

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "agent.run",
            "params": {"task": "say hello"},
        }) + "\n"
        client_writer.write(request.encode())
        await client_writer.drain()

    lines = []

    async def read_responses():
        while True:
            try:
                line = await asyncio.wait_for(client_reader.readline(), timeout=5.0)
                if not line:
                    break
                lines.append(json.loads(line))
            except asyncio.TimeoutError:
                break

    with patch("sediman.rpc_server._get_agent_loop", new_callable=AsyncMock, return_value=mock_agent), \
         patch("sediman.rpc_server.InterruptSignal") as mock_interrupt:
        mock_interrupt.get.return_value = MagicMock()
        mock_interrupt.get.return_value.is_set.return_value = False
        mock_interrupt.get.return_value.clear = MagicMock()

        test_task = asyncio.create_task(run_test())
        await asyncio.sleep(0.1)
        await read_responses()
        await test_task

    if client_writer:
        client_writer.close()
    server.close()
    try:
        os.unlink(sock_path)
    except Exception:
        pass

    streaming_msgs = [l for l in lines if l.get("method") == "chat.streaming"]

    assert len(streaming_msgs) == 11, f"Expected 11 streaming msgs (one per char in 'Hello world'), got {len(streaming_msgs)}"

    phases = set(m.get("params", {}).get("phase") for m in streaming_msgs)
    assert "responding" in phases, f"Expected 'responding' phase, got phases: {phases}"

    for msg in streaming_msgs:
        assert "token" in msg.get("params", {}), f"Missing token in streaming msg: {msg}"
        assert msg.get("jsonrpc") == "2.0", f"Missing jsonrpc version: {msg}"


@pytest.mark.asyncio
async def test_step_notifications_arrive():
    """Verify chat.progress notifications arrive for step events."""
    from sediman.rpc_server import handle_connection
    from sediman.agent.loop import StepEvent

    sock_path = tempfile.mktemp(suffix=".sock")
    server = await asyncio.start_unix_server(handle_connection, path=sock_path)

    agent = MagicMock()
    mock_result = MagicMock()
    mock_result.result = "done"
    mock_result.steps = []
    mock_result.skill_created = None
    mock_result.actions_taken = []
    mock_result.scheduled_job_id = None
    mock_result.schedule_cron = None
    mock_result.iterations = 0
    mock_result.strategy_used = "direct"

    async def fake_run(task):
        if agent.on_step:
            agent.on_step(StepEvent(step=1, action="navigate", observation="ok", phase="executing"))
        return mock_result

    agent.run = fake_run
    agent.on_step = None
    agent.on_streaming_text = None

    client_reader = None
    client_writer = None

    async def run_test():
        nonlocal client_reader, client_writer
        await asyncio.sleep(0.05)
        client_reader, client_writer = await asyncio.open_unix_connection(sock_path)

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "agent.run",
            "params": {"task": "test"},
        }) + "\n"
        client_writer.write(request.encode())
        await client_writer.drain()

    lines = []

    async def read_responses():
        while True:
            try:
                line = await asyncio.wait_for(client_reader.readline(), timeout=5.0)
                if not line:
                    break
                lines.append(json.loads(line))
            except asyncio.TimeoutError:
                break

    with patch("sediman.rpc_server._get_agent_loop", new_callable=AsyncMock, return_value=agent), \
         patch("sediman.rpc_server.InterruptSignal") as mock_interrupt:
        mock_interrupt.get.return_value = MagicMock()
        mock_interrupt.get.return_value.is_set.return_value = False
        mock_interrupt.get.return_value.clear = MagicMock()

        test_task = asyncio.create_task(run_test())
        await asyncio.sleep(0.1)
        await read_responses()
        await test_task

    if client_writer:
        client_writer.close()
    server.close()
    try:
        os.unlink(sock_path)
    except Exception:
        pass

    progress_msgs = [l for l in lines if l.get("method") == "chat.progress"]

    print(f"\nTotal messages: {len(lines)}")
    print(f"Progress notifications: {len(progress_msgs)}")

    assert len(progress_msgs) > 0, f"Expected progress notifications but got none. Messages: {[json.dumps(l)[:80] for l in lines]}"
    assert progress_msgs[0]["params"]["action"] == "navigate"
    assert progress_msgs[0]["params"]["phase"] == "executing"
