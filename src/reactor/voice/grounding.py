"""Ground representational changes in the originating request, not scenario answers."""

import calendar
import re

from reactor.voice.dates import calendar_day


MONTH_DAY = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:st|nd|rd|th)?\b", re.I,
)


def _identifier_format(tool, identifier, transcript):
    """Remove model-added separators only with matching identifier evidence."""
    if not isinstance(identifier, str):
        return identifier
    value = identifier.strip()
    if re.fullmatch(r"[A-Za-z0-9](?:[\s,]+[A-Za-z0-9])+", value):
        return re.sub(r"[\s,]+", "", value)
    if not re.fullmatch(r"[A-Za-z0-9]+(?:[\s,-]+[A-Za-z0-9]+)+", value):
        return identifier
    # If the user supplied this punctuated identifier, do not reinterpret it
    # based on another compact identifier elsewhere in the same request.
    if re.search(r"(?<![A-Za-z0-9_-])" + re.escape(value) + r"(?![A-Za-z0-9_-])", transcript, re.I):
        return identifier
    contexts = {
        "track_order": r"order(?:\s+(?:id|number|code))?|tracking(?:\s+(?:id|number|code))?|track|number|reference",
        "update_identity_doc": r"passport|visa|document|identity|licen[cs]e|number|reference",
        "add_to_cart": r"product(?:\s+(?:id|number|code))?|item|number|reference",
    }
    compact = re.sub(r"[\s,-]+", "", value)
    spelling = r"[\s,]*".join(re.escape(character) for character in compact) + r"(?![A-Za-z0-9_-])"
    prefix = r"\b(?:" + contexts[tool] + r")\b(?:\s+(?:number|id|is|was|to|as)\b)*[\s:]*"
    for context in re.finditer(prefix, transcript, re.I):
        following = transcript[context.end():]
        match = re.match(spelling, following, re.I)
        if match:
            next_token = re.match(r"[\s,]+([A-Za-z0-9_-]+)", following[match.end():])
            if next_token and (len(next_token.group(1)) == 1 or re.search(r"[0-9_-]", next_token.group(1))):
                continue  # a longer spelling, not a complete identifier match
            return compact
    return identifier


def ground_request_arguments(tool, arguments, transcript, *, identifier_transcript=None):
    args = dict(arguments)
    field = {"track_order": "order_id", "update_identity_doc": "doc_number", "add_to_cart": "product_id"}.get(tool)
    identifier = args.get(field) if field else None
    if field and field in args:
        evidence = transcript if identifier_transcript is None else identifier_transcript
        # Prefer the correction portion of a single transcript as well as the
        # last meaningful turn. Older compact evidence cannot erase a dash the
        # user subsequently dictated.
        corrections = list(re.finditer(r"\b(?:actually|instead|i meant|no,? wait)\b", evidence, re.I))
        if corrections:
            evidence = evidence[corrections[-1].end():]
        args[field] = _identifier_format(tool, identifier, evidence)

    if tool == "search_flights":
        day = calendar_day(args.get("date"))
        # Only remove a model-added year with matching month/day evidence. Do
        # not translate relative dates, change the requested day, or discard a
        # year present anywhere in this request's accumulated transcript.
        if (day is not None and isinstance(args.get("date"), str)
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", args["date"])
                and not re.search(r"\b\d{4}\b", transcript)):
            mentioned = [calendar_day(match.group()) for match in MONTH_DAY.finditer(transcript)]
            if any(item is not None and item[:2] == day[:2] for item in mentioned):
                args["date"] = f"{calendar.month_name[day[0]]} {day[1]}"
    return args
