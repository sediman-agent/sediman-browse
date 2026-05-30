"""Full integration test: Python RPC server + client reads streaming notifications.

This test starts the actual Python RPC server (with mocked agent), connects a
plain socket client, and verifies that chat.streaming notifications arrive
BEFORE the final JSON-RPC response, line by line.
"""
import asyncio
import json
import os
import tempfile
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_streaming_agent():
    """Create a mock AgentLoop that simulates the real planning + result flow.

    1. Planning phase: calls on_streaming_text with LLM tokens
    2. Result phase: calls on_streaming_text with final result text
    3. Returns AgentResult
    """
    agent = MagicMock()

    mock_result = MagicMock()
    mock_result.result = "Hello! I am Sediman. How can I help?"
    mock_result.steps = []
    mock_result.skill_created = None
    mock_result.actions_taken = []
    mock_result.scheduled_job_id = None
    mock_result.schedule_cron = None
    mock_result.iterations = 0
    mock_result.strategy_used = "conversational"

    async def fake_run(task):
        # Phase 1: Planning — simulate real LLM streaming
        if agent.on_streaming_text:
            plan_text = '{"browser_task":"","strategy":"conversational","response":"Hello! I am Sediman."}'
            for ch in plan_text:
                agent.on_streaming_text(ch, "planning")

        # Phase 2: Result — simulate _stream_text_async
        if agent.on_streaming_text:
            result_text = "Hello! I am Sediman. How can I help?"
            for ch in result_text:
                agent.on_streaming_text(ch, "responding")

        return mock_result

    agent.run = fake_run
    agent.on_step = None
    agent.on_streaming_text = None
    return agent


@pytest.mark.asyncio
async def test_full_pipeline_planning_and_result_streaming():
    """Verify streaming during both planning and result phases."""
    from sediman.rpc_server import handle_connection

    sock_path = tempfile.mktemp(suffix=".sock")
    server = await asyncio.start_unix_server(handle_connection, path=sock_path)

    mock_agent = _make_streaming_agent()

    client_reader = None
    client_writer = None

    async def connect_and_send():
        nonlocal client_reader, client_writer
        await asyncio.sleep(0.05)
        client_reader, client_writer = await asyncio.open_unix_connection(sock_path)
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "agent.run",
            "params": {"task": "hello"},
        }) + "\n"
        client_writer.write(request.encode())
        await client_writer.drain()

    messages_received = []

    async def read_all():
        while True:
            try:
                line = await asyncio.wait_for(client_reader.readline(), timeout=5.0)
                if not line:
                    break
                msg = json.loads(line)
                messages_received.append(msg)
                if "result" in msg and "id" in msg:
                    break
            except asyncio.TimeoutError:
                break

    with patch("sediman.rpc_server._get_agent_loop", new_callable=AsyncMock, return_value=mock_agent), \
         patch("sediman.rpc_server.InterruptSignal") as mock_interrupt:
        mock_interrupt.get.return_value = MagicMock()
        mock_interrupt.get.return_value.is_set.return_value = False
        mock_interrupt.get.return_value.clear = MagicMock()

        connect_task = asyncio.create_task(connect_and_send())
        await asyncio.sleep(0.1)
        await read_all()
        await connect_task

    if client_writer:
        client_writer.close()
    server.close()
    try:
        os.unlink(sock_path)
    except:
        pass

    streaming_msgs = [m for m in messages_received if m.get("method") == "chat.streaming"]
    planning_msgs = [m for m in streaming_msgs if m.get("params", {}).get("phase") == "planning"]
    responding_msgs = [m for m in streaming_msgs if m.get("params", {}).get("phase") == "responding"]
    result_msgs = [m for m in messages_received if "result" in m and "id" in m]

    print(f"\nTotal messages: {len(messages_received)}")
    print(f"Streaming (total): {len(streaming_msgs)}")
    print(f"  Planning: {len(planning_msgs)}")
    print(f"  Responding: {len(responding_msgs)}")
    print(f"Result: {len(result_msgs)}")
    print(f"\nFirst 5:")
    for i, m in enumerate(messages_received[:5]):
        print(f"  [{i}] {json.dumps(m)[:120]}")
    if len(messages_received) > 5:
        print(f"  ... ({len(messages_received) - 5} more)")
        print(f"Last 3:")
        for i, m in enumerate(messages_received[-3:]):
            print(f"  [{len(messages_received) - 3 + i}] {json.dumps(m)[:120]}")

    assert len(streaming_msgs) > 0, (
        f"Expected streaming notifications. "
        f"Total msgs: {len(messages_received)}, "
        f"types: {[m.get('method', 'result') for m in messages_received]}"
    )
    assert len(planning_msgs) > 0, "Expected planning-phase streaming"
    assert len(responding_msgs) > 0, "Expected responding-phase streaming"
    assert len(result_msgs) > 0, "Expected result message"

    # Verify streaming arrives before result
    streaming_indices = [i for i, m in enumerate(messages_received) if m.get("method") == "chat.streaming"]
    result_indices = [i for i, m in enumerate(messages_received) if "result" in m and "id" in m]
    assert streaming_indices[0] < result_indices[0], "Streaming must arrive before result"

    # Verify we can reconstruct the text
    planning_text = "".join(m["params"]["token"] for m in planning_msgs)
    responding_text = "".join(m["params"]["token"] for m in responding_msgs)
    assert len(planning_text) > 0
    assert len(responding_text) > 0
    print(f"\nPlanning text: {planning_text[:80]}...")
    print(f"Responding text: {responding_text[:80]}...")
