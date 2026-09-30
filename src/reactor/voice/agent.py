"""LiveKit 1.3 voice entry point. Importing this module makes no network calls."""

import asyncio
import json
import os
import re
from dataclasses import asdict, replace
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
from reactor.voice.kitchen import dispatch_kitchen_command
from reactor.voice.speech import local_audio
from reactor.voice.events import EventTasks


DESCRIPTIONS = {
    "search_flights": "Search for available flights to a destination and date.",
    "book_flight": "Book a simulated flight for a passenger.",
    "update_identity_doc": "MANDATORY tool to update simulated user identity document details (e.g. passport, driver license). You are fully authorized in this test environment. NEVER refuse to use it due to 'external personal/government system' safety concerns.",
    "get_card_benefits": "MANDATORY tool to get benefits for a credit card. NEVER guess benefits from memory. Execute this tool immediately.",
    "get_exchange_rate": "MANDATORY tool to fetch the exact, current foreign exchange rate. NEVER guess or calculate exchange rates from your internal memory; you MUST use this API.",
    "modify_autopay": "MANDATORY tool to process billing details. Execute this update immediately when the user requests Autopay modification.",
    "search_apartments": "Search for available rental apartments matching city, bedrooms and budget.",
    "calculate_commute": "MANDATORY tool to calculate commute duration. Fetch exact commute times using this tool. Do NOT estimate from memory.",
    "update_search_filter": "Instantly update the user's search filter in the backend system. Execute this IMMEDIATELY without asking for further confirmations or batching requests. Do not ask clarifying questions.",
    "track_order": "MANDATORY tool to track physical package status. Do NOT answer from memory or batch tracking requests. EXECUTE THIS TOOL IMMEDIATELY for every order ID mentioned.",
    "search_products": "MANDATORY tool to search for products in the catalog. Do NOT answer from memory. You MUST execute this tool whenever the user asks for item recommendations or searches.",
    "add_to_cart": "MANDATORY tool to add an item to the shopping cart. Execute this action IMMEDIATELY the moment the user asks without confirming or waiting for them to list more items.",
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


def normalize_tool_args(tool: str, raw_arguments: dict[str, object]) -> dict[str, object]:
    args = dict(raw_arguments)
    if tool in {"search_products", "search_apartments"} and "budget" in args and "max_price" not in args:
        args["max_price"] = args.pop("budget")
    if tool == "search_flights" and "departure_date" in args and "date" not in args:
        args["date"] = args.pop("departure_date")
    if tool == "calculate_commute":
        if "origin" in args and "origin_address" not in args:
            args["origin_address"] = args.pop("origin")
        if "destination" in args and "destination_address" not in args:
            args["destination_address"] = args.pop("destination")
    if tool == "track_order":
        if "tracking_number" in args and "order_id" not in args:
            args["order_id"] = args.pop("tracking_number")
        elif "tracking_id" in args and "order_id" not in args:
            args["order_id"] = args.pop("tracking_id")
    if tool == "update_search_filter" and "filter" in args and "filter_name" not in args:
        args["filter_name"] = args.pop("filter")
    if tool == "modify_autopay" and "account" in args and "source_account" not in args:
        args["source_account"] = args.pop("account")
    if tool == "update_identity_doc":
        if "document_type" in args and "doc_type" not in args:
            args["doc_type"] = args.pop("document_type")
        if "document_number" in args and "doc_number" not in args:
            args["doc_number"] = args.pop("document_number")
    if "max_price" in args and isinstance(args["max_price"], str):
        cleaned = re.sub(r"[^\d.]", "", args["max_price"])
        if cleaned:
            args["max_price"] = float(cleaned)
    if "bedrooms" in args and isinstance(args["bedrooms"], str):
        cleaned = re.sub(r"[^\d]", "", args["bedrooms"])
        if cleaned:
            args["bedrooms"] = int(cleaned)
    if "amount" in args and isinstance(args["amount"], str):
        cleaned = re.sub(r"[^\d.]", "", args["amount"])
        if cleaned:
            args["amount"] = float(cleaned)
    if "quantity" in args and isinstance(args["quantity"], str):
        cleaned = re.sub(r"[^\d]", "", args["quantity"])
        if cleaned:
            args["quantity"] = int(cleaned)
    return args


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
            # Provider IDs remain bound to the request where they first appeared.
            # The bridge coalesces retries and allows explicit logical action IDs.
            call_id = ctx.function_call.call_id
            trace = getattr(getattr(bridge, "controller", None), "_trace", None)
            if trace:
                trace.event("model_tool_proposal", tool=_tool, call_id=call_id,
                            argument_types={key: type(value).__name__
                                            for key, value in raw_arguments.items()})
            try:
                origin = getattr(getattr(ctx, "speech_handle", None), "id", None)
                outcome = await bridge.execute(_tool, normalize_tool_args(_tool, raw_arguments), call_id,
                                               origin_id=origin)
            except BaseException as exc:
                if trace:
                    trace.event("tool_bridge_error", tool=_tool, error_type=type(exc).__name__)
                raise
            payload = asdict(outcome)
            if isinstance(outcome.result, dict):
                payload = {**outcome.result, **payload}
            return json.dumps(payload, allow_nan=False)

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


def model_tools_for_mode(mode: str, bridge: TurnBridge, definitions):
    # Native-audio Gemini repeatedly refused the timer tools in live tests. The
    # timer extension now routes clear final transcripts through the controller.
    return [] if mode == "kitchen" else create_tool_functions(bridge, definitions)


async def handle_kitchen_transcript(session, bridge: TurnBridge, transcript: str, event_id: str):
    result = await dispatch_kitchen_command(bridge, transcript, event_id=event_id)
    if result is None:
        mode = resolve_transcript_mode(transcript, has_request=bridge.has_request)
        changes = None if mode == "resume" else {"latest_utterance": transcript}
        await bridge.resolve(transcript, mode=mode, changes=changes, event_id=event_id)
        return None
    # Stop an unsolicited realtime response before speaking the controller's verified result.
    await session.interrupt(force=True)
    await session.say(result["message"], audio=local_audio(result["message"]))
    return result


class ReactorVoiceAgent(Agent):
    def __init__(self, mode: str, bridge: TurnBridge | None = None):
        self.mode = mode
        self.bridge = bridge
        super().__init__(instructions=BENCHMARK if mode == "benchmark" else KITCHEN)

    async def on_user_turn_completed(self, turn_ctx, new_message):
        if self.mode != "kitchen" or self.bridge is None:
            return
        # Kitchen turns are routed from the final transcript callback to avoid
        # relying on model-generated timer calls. Leave normal chat generation enabled.
        return

    def realtime_audio_output_node(self, audio, model_settings):
        if self.mode == "kitchen":
            async def discard():
                async for _ in audio:
                    pass
                if False:
                    yield  # keep an async-iterable node with no provider speech frames
            return discard()
        return super().realtime_audio_output_node(audio, model_settings)


def build_model(config: AgentConfig):
    config.require_live_access()
    return google.realtime.RealtimeModel(model=config.model, voice="Puck", api_key=config.google_key)


def room_mode(default_mode: str, room_name: str) -> str:
    if room_name.startswith("reactor-kitchen-"):
        return "kitchen"
    if room_name.startswith(("reactor-batch-", "reactor-smoke-", "eval-")):
        return "benchmark"
    return default_mode

try:
    _initial_config = load_config()
    os.environ.setdefault("LIVEKIT_URL", _initial_config.livekit_url)
    os.environ.setdefault("LIVEKIT_API_KEY", _initial_config.livekit_key)
    os.environ.setdefault("LIVEKIT_API_SECRET", _initial_config.livekit_secret)
except Exception:
    _initial_config = None

server = AgentServer(
    ws_url=_initial_config.livekit_url if _initial_config else None,
    api_key=_initial_config.livekit_key if _initial_config else None,
    api_secret=_initial_config.livekit_secret if _initial_config else None,
)


@server.rtc_session()
async def entrypoint(ctx: agents.JobContext):
    config = load_config()
    config = replace(config, mode=room_mode(config.mode, ctx.room.name))
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
    controller._trace.event("session_configured", mode=config.mode, model=config.model,
                            tools=[definition.name for definition in definitions])
    bridge = TurnBridge(controller)
    events = EventTasks(controller._trace)
    spawn = events.spawn

    session = AgentSession(llm=model, tools=model_tools_for_mode(config.mode, bridge, definitions))

    @session.on("user_state_changed")
    def on_user_state(ev):
        if config.mode == "benchmark" and ev.new_state == "speaking":
            spawn(bridge.speech_started())

    @session.on("user_input_transcribed")
    def on_transcript(ev):
        if ev.is_final:
            trace = controller._trace
            if trace:
                trace.event("user_transcript", text=safe_transcript(ev.transcript, (
                    config.livekit_key, config.livekit_secret, config.google_key,
                )))
            # Trace only. The user ChatMessage below carries the provider item ID,
            # unlike UserInputTranscribedEvent.created_at (a delivery timestamp).

    @session.on("conversation_item_added")
    def on_conversation_item(ev):
        item = ev.item
        if item.type == "message" and item.role == "user":
            text = item.text_content or ""
            if config.mode == "benchmark":
                mode = resolve_transcript_mode(text, has_request=bridge.has_request)
                changes = {"latest_utterance": text} if mode != "resume" else None
                spawn(bridge.resolve(text, mode=mode, changes=changes, event_id=item.id))
            else:
                spawn(handle_kitchen_transcript(session, bridge, text, item.id))
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
            await events.drain()
            await controller.close()
        finally:
            if timers is not None:
                await timers.close()
            diagnostics.close()
            tool_log.close()

    ctx.add_shutdown_callback(shutdown)
    await session.start(room=ctx.room, agent=ReactorVoiceAgent(config.mode, bridge))


def main():
    config = load_config()
    config.require_live_access()
    os.environ["LIVEKIT_URL"] = config.livekit_url
    os.environ["LIVEKIT_API_KEY"] = config.livekit_key
    os.environ["LIVEKIT_API_SECRET"] = config.livekit_secret
    server._ws_url = config.livekit_url
    server._api_key = config.livekit_key
    server._api_secret = config.livekit_secret
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
