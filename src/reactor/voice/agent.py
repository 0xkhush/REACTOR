"""LiveKit 1.3 voice entry point. Importing this module makes no network calls."""

import asyncio
import inspect
import json
import os
import re
from dataclasses import asdict, replace
from pathlib import Path
from typing import Union

from jsonschema import ValidationError
from google.genai import types

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
from reactor.voice.native_types import JsonInteger, JsonNumber
from reactor.voice.arguments import normalize_argument_values


DESCRIPTIONS = {
    "search_flights": "Search for available flights to a destination and date.",
    "book_flight": "Book a simulated flight for a passenger.",
    "update_identity_doc": "Update simulated identity document details using the user's final document type and number. This simulated operation is authorized.",
    "get_card_benefits": "Fetch card benefits from the simulated service; do not guess from memory.",
    "get_exchange_rate": "Fetch a currency conversion for the final amount and currency pair; do not calculate rates from memory.",
    "modify_autopay": "Update the simulated bill's source account after the user finishes specifying or correcting it.",
    "search_apartments": "Search for available rental apartments matching city, bedrooms and budget.",
    "calculate_commute": "Fetch commute duration between the supplied locations; named destinations are valid. Do not estimate from memory.",
    "update_search_filter": "Update one supplied filter key and scalar value. A standalone filter update does not need a city, bedroom count or a separate apartment search.",
    "track_order": "Fetch shipping status for each final requested order ID. Do not track a superseded false-start ID.",
    "search_products": "Search the catalog for the final requested query and optional budget; do not invent recommendations.",
    "add_to_cart": "Add the final product ID and quantity requested by the user, using returned product IDs for dependent steps.",
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
    aliases = {
        "search_products": (("budget", "max_price"),),
        "search_apartments": (("budget", "max_price"),),
        "search_flights": (("departure_date", "date"),),
        "calculate_commute": (("origin", "origin_address"),
                              ("departure_address", "origin_address"),
                              ("destination", "destination_address"),
                              ("arrival_address", "destination_address")),
        "track_order": (("tracking_number", "order_id"), ("tracking_id", "order_id")),
        "update_search_filter": (("filter", "filter_name"), ("filter_type", "filter_name")),
        "modify_autopay": (("account", "source_account"),
                           ("new_source_account", "source_account"),
                           ("billing_source_account", "source_account")),
        "update_identity_doc": (("document_type", "doc_type"), ("document_number", "doc_number")),
        "get_exchange_rate": (("source_currency", "from_currency"),
                              ("target_currency", "to_currency"),
                              ("currency_from", "from_currency"),
                              ("currency_to", "to_currency")),
    }
    for source, target in aliases.get(tool, ()):
        if source in args and target not in args:
            args[target] = args.pop(source)
    if tool == "calculate_commute" and isinstance(args.get("mode"), str):
        modes = {"drive": "driving", "walk": "walking"}
        args["mode"] = modes.get(args["mode"].lower().strip(), args["mode"])
    if tool == "search_products":
        args.pop("category", None)
    return normalize_argument_values(tool, args)


def resolve_transcript_mode(transcript: str, *, has_request: bool) -> str:
    """Conservative turn-level heuristic, not an ASR or semantic slot parser."""
    if not has_request:
        return "new"
    if re.fullmatch(r"\s*(thanks|thank you|okay|ok|yes)\s*[.!?]?\s*", transcript, re.I):
        return "resume"
    if re.search(r"\b(actually|instead|sorry|i meant|rather|no, wait)\b", transcript, re.I):
        return "correction"
    # Realtime VAD can split a single sentence at a hesitation. Clear connective
    # fragments keep the request token, so equivalent repeated proposals coalesce.
    # A command inside the fragment still starts a new task.
    text = re.sub(r"^\s*(?:(?:um|uh|er)[,.]?\s+)+", "", transcript, flags=re.I).strip()
    continuation = re.match(
        r"(?:during|because|so that|which|to make sure|"
        r"i (?:just )?(?:want|wanted) to (?:make sure|be sure|be certain))\b", text, re.I,
    )
    new_action = re.search(
        r"\b(?:track|search|find|book|reserve|update|modify|change|convert|calculate|"
        r"compare|add|remove|cancel|set|create|list|check|show|get|tell|status|"
        r"flight|order|conversion|benefits|autopay|apartment|filter|timer)\b", text, re.I,
    )
    if continuation and not new_action:
        return "resume"
    return "new"


def create_tool_functions(bridge: TurnBridge, definitions):
    tools = []
    for definition in definitions:
        raw_schema = {
            "name": definition.name,
            "description": DESCRIPTIONS[definition.name],
            "parameters": definition.schema,
        }

        async def invoke(raw_arguments: dict[str, object], ctx: RunContext, *,
                         _tool=definition.name, _schema=definition.schema) -> str:
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
                arguments = normalize_tool_args(_tool, raw_arguments)
                for key, property_schema in _schema["properties"].items():
                    if "default" in property_schema:
                        arguments.setdefault(key, property_schema["default"])
                outcome = await bridge.execute(_tool, arguments, call_id,
                                                origin_id=origin)
            except BaseException as exc:
                if trace:
                    trace.event("tool_bridge_error", tool=_tool, error_type=type(exc).__name__)
                if isinstance(exc, ValidationError):
                    # A rejected proposal has not reached the backend. Explain the
                    # contract using schema metadata only, never exception values.
                    fields = {key: spec["type"] for key, spec in _schema["properties"].items()}
                    raise agents.ToolError(
                        f"{_tool} was not executed: invalid arguments. "
                        f"Required fields: {', '.join(_schema.get('required', []))}. "
                        f"Allowed fields and types: {json.dumps(fields)}. "
                        "Repair the proposal using only values supplied by the user or prior tool results. "
                        "Do not invent missing values or claim success."
                    ) from None
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


def native_function_tool(raw_tool, definition):
    """Expose the same dispatcher through LiveKit's native Gemini schema path.

    SDK introspection uses this explicit signature and annotations to build its
    typed parameters. The callable still sends actual arguments to the validated
    controller boundary; no generated source, eval, or SDK monkeypatch is needed.
    """
    async def handler(**arguments):
        ctx = arguments.pop("ctx")
        # SDK argument models ignore extras. Revalidate the complete provider
        # payload rather than silently executing only its recognized subset.
        provider_arguments = getattr(ctx.function_call, "arguments", None)
        if isinstance(provider_arguments, str):
            arguments = json.loads(provider_arguments)
        return await raw_tool(raw_arguments=arguments, ctx=ctx)

    annotations = {"ctx": RunContext, "return": str}
    parameters = [inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, annotation=RunContext)]
    schema = definition.schema
    # LiveKit 1.3 discards non-Field Annotated metadata when preparing arguments.
    # Core-schema number types retain strictness through that SDK conversion.
    python_types = {"string": str, "number": JsonNumber,
                    "integer": JsonInteger, "boolean": bool, "null": type(None)}
    for name, spec in schema["properties"].items():
        kind = spec["type"]
        if isinstance(kind, list):
            annotation = Union[tuple(python_types[item] for item in kind)]
        else:
            annotation = python_types[kind]
        annotations[name] = annotation
        default = inspect.Parameter.empty if name in schema.get("required", []) else spec.get("default")
        parameters.append(inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY,
                                            annotation=annotation, default=default))
    handler.__name__ = definition.name
    handler.__annotations__ = annotations
    handler.__signature__ = inspect.Signature(parameters, return_annotation=str)
    return llm.function_tool(name=definition.name, description=DESCRIPTIONS[definition.name])(handler)


def model_tools_for_mode(mode: str, bridge: TurnBridge, definitions):
    # Native-audio Gemini repeatedly refused the timer tools in live tests. The
    # timer extension now routes clear final transcripts through the controller.
    if mode == "kitchen":
        return []
    raw_tools = create_tool_functions(bridge, definitions)
    return [native_function_tool(tool, definition) for tool, definition in zip(raw_tools, definitions)]


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
    options = {}
    if config.mode == "benchmark":
        options["realtime_input_config"] = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                silence_duration_ms=2000,
            ),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
        )
    return google.realtime.RealtimeModel(model=config.model, voice="Puck", api_key=config.google_key, **options)


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
