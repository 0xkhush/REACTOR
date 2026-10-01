import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from livekit.agents import llm

from reactor.config import AgentConfig
from reactor.controller import Controller
from reactor.voice.events import EventTasks
from reactor.voice import agent


@pytest.fixture
async def runtime(monkeypatch, tmp_path):
    """Exercise actual entrypoint event wiring; substitute only room/model IO."""
    monkeypatch.chdir(tmp_path)
    config = AgentConfig("wss://example.livekit.cloud", "test-key", "test-secret", "test-google",
                         model="test-model", free_quota_confirmed=True)
    monkeypatch.setattr(agent, "load_config", lambda: config)
    monkeypatch.setattr(agent, "build_model", lambda config: object())
    monkeypatch.setattr(agent, "Path", lambda value: (
        tmp_path / "calls.jsonl" if str(value) == "/tmp/agent_tool_calls.log" else Path(value)))
    state = {}

    class Session:
        def __init__(self, *, llm, tools):
            self.handlers = {}
            self.tools = {tool.info.name: tool for tool in tools}
            state["session"] = self

        def on(self, name):
            def register(callback):
                self.handlers[name] = callback
                return callback
            return register

        async def start(self, **kwargs):
            pass

        def emit(self, name, event):
            if name in self.handlers:
                self.handlers[name](event)

        async def call(self, name, arguments, call_id):
            payload = json.dumps(arguments)
            ctx = SimpleNamespace(function_call=SimpleNamespace(call_id=call_id, arguments=payload))
            tool = self.tools[name]
            args, kwargs = llm.utils.prepare_function_arguments(fnc=tool, json_arguments=payload, call_ctx=ctx)
            return json.loads(await tool(*args, **kwargs))

    def controller(*args):
        state["controller"] = Controller(*args)
        return state["controller"]

    def events(trace):
        state["events"] = EventTasks(trace)
        return state["events"]

    monkeypatch.setattr(agent, "AgentSession", Session)
    monkeypatch.setattr(agent, "Controller", controller)
    monkeypatch.setattr(agent, "EventTasks", events)
    shutdown = []
    ctx = SimpleNamespace(room=SimpleNamespace(name="reactor-batch-event-test"),
                          add_shutdown_callback=shutdown.append)
    await agent.entrypoint(ctx)
    try:
        yield state
    finally:
        for callback in shutdown:
            await callback()


def user_item(text, item_id):
    return SimpleNamespace(item=SimpleNamespace(type="message", role="user", text_content=text, id=item_id))


async def test_synthetic_speech_state_after_tool_result_does_not_deadlock_next_step(runtime):
    session = runtime["session"]
    session.emit("conversation_item_added", user_item("Find a desk and add it to my cart", "turn-1"))
    await runtime["events"].drain()
    search = await session.call("search_products", {"query": "desk"}, "search-1")
    # Google 1.3.12 emits input_speech_started for its own tool-result generation.
    session.emit("user_state_changed", SimpleNamespace(new_state="speaking"))
    await runtime["events"].drain()
    cart = await asyncio.wait_for(session.call("add_to_cart", {
        "product_id": search["result"]["products"][0]["product_id"], "quantity": 2,
    }, "cart-1"), timeout=1)
    assert cart["status"] == "succeeded"
    assert cart["result"]["quantity"] == 2
    assert [op["status"] for op in runtime["controller"].snapshot()["operations"]] == ["succeeded", "succeeded"]


async def test_real_partial_transcript_holds_dispatch_until_provider_final_resolves(runtime):
    session = runtime["session"]
    session.emit("conversation_item_added", user_item("Find a desk", "turn-1"))
    await runtime["events"].drain()
    session.emit("user_input_transcribed", SimpleNamespace(is_final=False, transcript="Actually a chair"))
    await runtime["events"].drain()
    assert not runtime["controller"].snapshot()["resolved"]
    pending = asyncio.create_task(session.call("search_products", {"query": "desk"}, "old-call"))
    try:
        # Yield until the proposal is registered, rather than relying on elapsed wall time.
        for _ in range(10):
            await asyncio.sleep(0)
            if runtime["controller"].snapshot()["operations"]:
                break
        assert not pending.done()
        session.emit("conversation_item_added", user_item("Actually a chair", "turn-2"))
        await runtime["events"].drain()
        old = await asyncio.wait_for(pending, 1)
        assert old["status"] == "cancelled_before_dispatch"
        current = await session.call("search_products", {"query": "chair"}, "new-call")
        assert current["status"] == "succeeded"
        assert current["result"]["products"][0]["name"] == "chair Premium"
    finally:
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def test_empty_and_late_final_transcription_notifications_do_not_reopen_resolved_input(runtime):
    session = runtime["session"]
    session.emit("conversation_item_added", user_item("Find a desk", "turn-1"))
    await runtime["events"].drain()
    session.emit("user_input_transcribed", SimpleNamespace(is_final=False, transcript="  "))
    session.emit("user_input_transcribed", SimpleNamespace(is_final=True, transcript="Find a desk"))
    await runtime["events"].drain()
    result = await asyncio.wait_for(session.call("search_products", {"query": "desk"}, "search-1"), 1)
    assert result["status"] == "succeeded"
