"""Conservative argument formatting, independent of benchmark scenarios."""

import math
import re

from reactor.voice.turns import calendar_day


def _number(value, *, integer=False, money=False):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if money:
        if text[:1] in {"$", "£", "€"}:
            text = text[1:].strip()
        elif len(text) > 1 and text[0] in "+-" and text[1] in "$£€":
            text = text[0] + text[2:].strip()
    whole = r"(?:\d+|\d{1,3}(?:,\d{3})+)"
    pattern = rf"[+-]?{whole}" if integer else rf"[+-]?{whole}(?:\.\d+)?(?:[eE][+-]?\d+)?"
    if not re.fullmatch(pattern, text):
        return value
    text = text.replace(",", "")
    if integer or not re.search(r"[.eE]", text):
        return int(text)
    parsed = float(text)
    return parsed if math.isfinite(parsed) else value


def normalize_argument_values(tool: str, arguments: dict) -> dict:
    args = dict(arguments)
    for key in ("max_price", "amount"):
        if key in args:
            args[key] = _number(args[key], money=True)
    for key in ("bedrooms", "quantity"):
        if key in args:
            args[key] = _number(args[key], integer=True)

    date = args.get("date")
    if tool == "search_flights" and isinstance(date, str) and calendar_day(date) is not None:
        args["date"] = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", date, flags=re.I)

    account = args.get("source_account")
    if tool == "modify_autopay" and isinstance(account, str):
        category = re.fullmatch(r"(checking|savings|current)\s+(?:bank\s+)?account", account.strip(), re.I)
        if category:
            args["source_account"] = category.group(1).lower()

    document = args.get("doc_type")
    if tool == "update_identity_doc" and isinstance(document, str):
        label = document.lower().strip().replace("_", " ").replace("-", " ")
        if re.fullmatch(r"driver(?:'s|s)? (?:license|licence)", label):
            args["doc_type"] = "driver_license"
        elif label in {"id card", "identity card"}:
            args["doc_type"] = "id_card"
    return args
