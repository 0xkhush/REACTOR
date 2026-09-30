"""Conservative deterministic grammar for the timer-only extension."""

import re
from typing import Any

NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60,
}
DURATION = re.compile(r"\b(?P<value>\d+|[a-z]+(?:-[a-z]+)?)\s*(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)\b", re.I)
NAMED = re.compile(r"\b(?:called|named)\s+([a-z][a-z0-9_-]*)\b", re.I)


def _duration(match) -> int | None:
    raw = match.group("value").lower()
    if raw.isdigit():
        number = int(raw)
    else:
        parts = raw.split("-")
        values = [NUMBERS.get(part) for part in parts]
        if any(value is None for value in values):
            return None
        number = sum(values)
    unit = match.group("unit").lower()
    factor = 3600 if unit.startswith(("hour", "hr")) else 60 if unit.startswith(("minute", "min")) else 1
    seconds = number * factor
    return seconds if 0 < seconds <= 86400 else None


def _timer_name(text: str) -> str:
    explicit = NAMED.search(text)
    if explicit:
        return explicit.group(1).lower()
    before_timer = re.search(r"\b([a-z][a-z0-9_-]*)\s+timer\b", text, re.I)
    if before_timer and before_timer.group(1).lower() not in {"a", "an", "the"}:
        return before_timer.group(1).lower()
    return "timer"


def parse_timer_command(transcript: str) -> dict | None:
    text = transcript.strip().lower()
    if not text:
        return None
    if re.search(r"\b(?:don't|do not|not|never|maybe|perhaps|not sure|or later|minus|negative)\b", text):
        return None
    actions = re.findall(r"\b(?:set|start|create|cancel|stop|clear|list|show)\b", text)
    if len(actions) != 1 or len(NAMED.findall(text)) > 1:
        return None
    if re.search(r"\b(?:list|show)\b.*\btimers?\b", text):
        return {"action": "list"}
    if re.search(r"\b(?:cancel|stop|clear)\b.*\btimer\b", text):
        return {"action": "cancel", "name": _timer_name(text)}
    if not re.search(r"\b(?:set|start|create|make)\b.*\btimer\b", text):
        return None
    durations = list(DURATION.finditer(text))
    if not durations:
        return None
    for match in durations:
        preceding = text[:match.start()].rstrip()
        word = preceding.split()[-1] if preceding else ""
        if preceding.endswith((".", "-")) or word in NUMBERS or word in {"point", "hundred", "thousand"}:
            return None
    if re.search(r"\b(?:maybe|perhaps|not sure|or later)\b", text):
        return None
    if len(durations) > 1 and not re.search(r"\b(?:actually|instead|sorry|make it|make that)\b", text):
        return None
    # In a self-correction, the final explicit duration supersedes earlier values.
    seconds = _duration(durations[-1])
    if seconds is None:
        return None
    return {"action": "create", "name": _timer_name(text), "duration_seconds": seconds}


async def dispatch_kitchen_command(bridge, transcript: str, *, event_id: str) -> dict[str, Any] | None:
    """Execute only unambiguous timer commands after final transcript resolution."""
    command = parse_timer_command(transcript)
    if command is None:
        return None
    if not event_id:
        raise ValueError("A turn ID is required for idempotent timer dispatch")
    mode = "correction" if bridge.has_request and re.search(
        r"\b(actually|instead|sorry|i meant|rather|no, wait)\b", transcript, re.I
    ) else "new"
    slots = {key: value for key, value in command.items() if key != "action"}
    request = await bridge.resolve(transcript, mode=mode, changes=slots, event_id=event_id)

    if command["action"] == "create":
        outcome = await bridge.execute("create_timer", {
            "name": command["name"], "duration_seconds": command["duration_seconds"],
        }, f"kitchen:{event_id}:create", request=request)
        if outcome.status != "succeeded" or outcome.superseded or outcome.result is None:
            return {"handled": True, "message": "I couldn't confirm the timer was created.",
                    "timer": None, "outcome": outcome}
        return {"handled": True, "message": (
            f"Timer {outcome.result['name']} set for {int(outcome.result['duration_seconds'])} seconds."
        ), "timer": outcome.result, "outcome": outcome}

    if command["action"] == "list":
        outcome = await bridge.execute("list_timers", {}, f"kitchen:{event_id}:list", request=request)
        if outcome.status != "succeeded" or outcome.superseded or outcome.result is None:
            return {"handled": True, "message": "I couldn't verify the timer list.",
                    "timers": None, "outcome": outcome}
        timers = outcome.result["timers"] if outcome.result else []
        return {"handled": True, "message": f"There are {len(timers)} timers.",
                "timers": timers, "outcome": outcome}

    listing = await bridge.execute("list_timers", {}, f"kitchen:{event_id}:list", request=request)
    if listing.status != "succeeded" or listing.superseded or listing.result is None:
        return {"handled": True, "message": "I couldn't verify the timer list to cancel that timer.",
                "timer": None, "outcome": listing}
    matches = [timer for timer in (listing.result or {}).get("timers", [])
               if timer["name"].casefold() == command["name"].casefold() and timer["state"] == "running"]
    if len(matches) != 1:
        message = (f"I found multiple active timers named {command['name']}; tell me which one."
                   if matches else f"I couldn't find an active timer named {command['name']}.")
        return {"handled": True, "message": message, "timer": None, "outcome": listing}
    outcome = await bridge.execute("cancel_timer", {"timer_id": matches[0]["timer_id"]},
                                   f"kitchen:{event_id}:cancel", request=request)
    timer = outcome.result
    if outcome.status != "succeeded" or outcome.superseded or not timer or timer["state"] != "cancelled":
        message = f"Timer {command['name']} was not cancelled."
    else:
        message = f"Cancelled timer {timer['name']}."
    return {"handled": True, "message": message, "timer": timer, "outcome": outcome}
