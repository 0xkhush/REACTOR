"""LiveKit 1.3 voice entry point. Importing this module makes no network calls."""

import asyncio
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, RunContext, llm
from livekit.plugins import google

from reactor.config import AgentConfig, load_config
from reactor.controller import Controller
from reactor.tools.benchmark import BenchmarkTools
from reactor.tools.timers import TimerService
from reactor.trace import TraceRecorder
from reactor.voice.prompts import BENCHMARK, KITCHEN
from reactor.voice.turns import TurnBridge


DESCRIPTIONS = {
    "search_flights": "Search for available flights to a destination and date.",
    "book_flight": "Book a simulated flight for a passenger.",
    "update_identity_doc": "Update a simulated identity document.",
    "get_card_benefits": "Fetch the benefits of a simulated card.",
    "get_exchange_rate": "Fetch the conversion for an amount and currency pair.",
    "modify_autopay": "Change a simulated billing source account.",
    "search_apartments": "Find apartments matching city, bedrooms and budget.",
    "calculate_commute": "Fetch commute duration between two addresses.",
    "update_search_filter": "Change a simulated apartment search filter.",
    "track_order": "Fetch the current shipping status for an order ID.",
    "search_products": "Search the catalog for products matching a query and optional budget.",
    "add_to_cart": "Add a returned product ID to the shopping cart.",
    "create_timer": "Start a named kitchen timer; duration_seconds is in seconds.",
    "list_timers": "List timer IDs, names, remaining time and current states.",
    "cancel_timer": "Cancel a timer by its ID; inspect returned state before confirming.",
}


def safe_transcript(text: str, secrets) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:500]


def tool_execution_summary(ev):
    return [{"tool": call.name, "is_error": output is None or output.is_error}
            for call, output in ev.zipped()]


def resolve_transcript_mode(transcript: str, *, has_request: bool) -> str:
    """Conservative turn-level heuristic, not an ASR or semantic slot parser."""
    if not has_request:
        return "new"
    if re.fullmatch(r"\s*(thanks|thank you|okay|ok|yes)\s*[.!?]?\s*", transcript, re.I):
        return "resume"
    if re.search(r"\b(actually|instead|sorry|i meant|rather|no, wait)\b", transcript, re.I):
        return "correction"
    return "new"


def create_tool_functions(bridge: TurnBridge, definitions):
    tools = []
    for definition in definitions:
        raw_schema = {
            "name": definition.name,
            "description": DESCRIPTIONS[definition.name],
            "parameters": definition.schema,
        }

        async def invoke(raw_arguments: dict[str, object], ctx: RunContext, *, _tool=definition.name) -> str:
            # A provider call ID is stable across retransmission, while a new call ID is
            # a distinct action even if its arguments happen to be equal.
            call_id = ctx.function_call.call_id
            trace = getattr(getattr(bridge, "controller", None), "_trace", None)
            if trace:
                trace.event("model_tool_proposal", tool=_tool, call_id=call_id,
                            argument_types={key: type(value).__name__
                                            for key, value in raw_arguments.items()})
            try:
                outcome = await bridge.execute(_tool, raw_arguments, call_id)
            except BaseException as exc:
                if trace:
                    trace.event("tool_bridge_error", tool=_tool, error_type=type(exc).__name__)
                raise
            return json.dumps(asdict(outcome), allow_nan=False)

        # Raw tools accept the actual argument dictionary plus a LiveKit RunContext.
        # Bind the name in a closure without leaking _tool as a model-facing parameter.
        async def handler(raw_arguments: dict[str, object], ctx: RunContext, _invoke=invoke) -> str:
            return await _invoke(raw_arguments, ctx)

        # Replace default-argument closure with a two-argument coroutine for SDK introspection.
        def make_handler(bound):
            async def tool_handler(raw_arguments: dict[str, object], ctx: RunContext) -> str:
                return await bound(raw_arguments, ctx)
            return tool_handler

        tools.append(llm.function_tool(raw_schema=raw_schema)(make_handler(handler)))
    return tools


class ReactorVoiceAgent(Agent):
    def __init__(self, mode: str):
        super().__init__(instructions=BENCHMARK if mode == "benchmark" else KITCHEN)


def build_model(config: AgentConfig):
    config.require_live_access()
    return google.realtime.RealtimeModel(model=config.model, voice="Puck", api_key=config.google_key)


server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: agents.JobContext):
    config = load_config()
    config.require_live_access()
    model = build_model(config)
    timers = TimerService() if config.mode == "kitchen" else None
    backend = BenchmarkTools() if config.mode == "benchmark" else None
    definitions = timers.definitions() if timers else backend.definitions()
    log_dir = Path("artifacts")
    log_dir.mkdir(exist_ok=True)
    diagnostics = (log_dir / "trace.jsonl").open("a", encoding="utf-8")
    # FDB's run_tool_benchmark.py reads this room-keyed actual-call log.
    tool_log = Path("/tmp/agent_tool_calls.log").open("a", encoding="utf-8")
    controller = Controller(ctx.room.name, definitions, TraceRecorder(ctx.room.name, diagnostics, tool_log))
    bridge = TurnBridge(controller)
    pending_events: set[asyncio.Task] = set()

    def spawn(coroutine):
        task = asyncio.create_task(coroutine)
        pending_events.add(task)
        task.add_done_callback(pending_events.discard)

    session = AgentSession(llm=model, tools=create_tool_functions(bridge, definitions))

    @session.on("user_state_changed")
    def on_user_state(ev):
        if ev.new_state == "speaking":
            spawn(bridge.speech_started())

    @session.on("user_input_transcribed")
    def on_transcript(ev):
        if ev.is_final:
            trace = controller._trace
            if trace:
                trace.event("user_transcript", text=safe_transcript(ev.transcript, (
                    config.livekit_key, config.livekit_secret, config.google_key,
                )))
            # Model transcription can arrive after a tool proposal on realtime APIs;
            # the bridge waits for the first resolved turn rather than using guesses.
            mode = resolve_transcript_mode(ev.transcript, has_request=bridge.has_request)
            changes = {"latest_utterance": ev.transcript} if mode != "resume" else None
            spawn(bridge.resolve(ev.transcript, mode=mode, changes=changes, event_id=ev.created_at))

    @session.on("conversation_item_added")
    def on_conversation_item(ev):
        item = ev.item
        if item.type == "message" and item.role == "assistant" and item.text_content:
            controller._trace.event("agent_transcript", text=safe_transcript(
                item.text_content, (config.livekit_key, config.livekit_secret, config.google_key),
            ))

    @session.on("function_tools_executed")
    def on_tool_events(ev):
        controller._trace.event("sdk_tool_events", calls=tool_execution_summary(ev))

    @session.on("error")
    def on_sdk_error(ev):
        controller._trace.event("sdk_error", error_type=type(ev.error).__name__)

    async def shutdown():
        try:
            await bridge.close()
            await asyncio.gather(*pending_events, return_exceptions=True)
            await controller.close()
        finally:
            if timers is not None:
                await timers.close()
            diagnostics.close()
            tool_log.close()

    ctx.add_shutdown_callback(shutdown)
    await session.start(room=ctx.room, agent=ReactorVoiceAgent(config.mode))


def main():
    config = load_config()
    config.require_live_access()
    os.environ["LIVEKIT_URL"] = config.livekit_url
    os.environ["LIVEKIT_API_KEY"] = config.livekit_key
    os.environ["LIVEKIT_API_SECRET"] = config.livekit_secret
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
