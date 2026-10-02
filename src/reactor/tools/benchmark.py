"""FDB-v3 mock API adapter; only the upstream registry supplies results."""

import importlib
import subprocess
import sys
from pathlib import Path

from reactor.tools.base import ToolDefinition


ROOT = Path(__file__).resolve().parents[3]
UPSTREAM = ROOT / "vendor" / "Full-Duplex-Bench"
REVISION = "3e799c45a045256f47d5f1c9cda90157e2d2ec9e"


def field(type_, *, default=None, optional=False):
    result = {"type": type_}
    if optional:
        result["default"] = default
    return result


# Model-facing tool contracts follow upstream lk_agent_tool.py; results come from mock_apis.py.
# Tool specifications contain API interfaces, never benchmark scenario metadata.
CONTRACTS = {
    "search_flights": (False, {"destination": field("string"), "date": field("string")}, ()),
    "book_flight": (True, {"passenger_name": field("string")}, ()),
    "update_identity_doc": (True, {"doc_type": field("string"), "doc_number": field("string")}, ()),
    "get_card_benefits": (False, {"card_type": field("string")}, ()),
    "get_exchange_rate": (False, {"amount": field("number"), "from_currency": field("string"),
                                  "to_currency": field("string")}, ()),
    "modify_autopay": (True, {"bill_type": field("string"), "source_account": field("string")}, ()),
    "search_apartments": (False, {"city": field("string"),
                                  "bedrooms": field("integer", optional=True, default=1),
                                  "max_price": field("number", optional=True, default=2000.0),
                                  "pets_allowed": field(["boolean", "null"], optional=True)},
                          ("bedrooms", "max_price", "pets_allowed")),
    "calculate_commute": (False, {"origin_address": field("string"), "destination_address": field("string"),
                                  "mode": field("string", optional=True, default="driving")}, ("mode",)),
    # mock_apis.update_search_filter accepts Any: preserve scalar values instead
    # of copying lk_agent_tool's narrower string-only hint and losing JSON types.
    "update_search_filter": (True, {"filter_name": field("string"),
                                    "value": field(["string", "number", "integer", "boolean"])}, ()),
    "track_order": (False, {"order_id": field("string")}, ()),
    "search_products": (False, {"query": field("string"),
                                "max_price": field(["number", "null"], optional=True)}, ("max_price",)),
    "add_to_cart": (True, {"product_id": field("string"),
                            "quantity": field("integer", optional=True, default=1)}, ("quantity",)),
}


# These are API argument instructions, not per-scenario answers. Native LiveKit
# schemas carry them to Gemini so it need not infer the contract from tool names.
FIELD_GUIDANCE = {
    "search_flights": {
        "destination": "The city or airport requested by the user. Use a full city name for an unambiguous common city alias; preserve explicit airport codes.",
        "date": "The final requested travel date. Use month name and day when no year was stated. Never add the current or next year. Retain a stated year and heed corrections.",
    },
    "book_flight": {"passenger_name": "The exact passenger name supplied by the user, retaining all given name components."},
    "update_identity_doc": {
        "doc_type": "The document category the user requested, such as passport, visa, driver_license or id_card. This simulated update is authorized.",
        "doc_number": "The complete user-supplied identifier. Join separately dictated letters and digits unless the user explicitly supplies separators. Count repeated characters; do not shorten the identifier.",
    },
    "get_card_benefits": {
        "card_type": "The stated card category or tier, not a generic suffix 'card' or 'credit card'. Keep a genuinely named issuer product intact.",
    },
    "get_exchange_rate": {
        "amount": "The final corrected numeric amount. Keep the direction of conversion and the stated amount; never substitute a prior false start.",
        "from_currency": "The source currency as a three-letter currency code.",
        "to_currency": "The target currency as a three-letter currency code.",
    },
    "modify_autopay": {
        "bill_type": "The bill whose autopay the user asked to modify. Perform separate updates for separate requested bills.",
        "source_account": "The final source account. Use a category such as checking or savings for those generic account types; preserve a specific named or numbered account.",
    },
    "search_apartments": {
        "city": "The requested city. Searching is distinct from a standalone filter update.",
        "bedrooms": "The latest stated bedroom count. Use the default only if the user gave no count.",
        "max_price": "The latest stated maximum monthly rent. Do not use the default if the user supplied a budget.",
        "pets_allowed": "The user's pet constraint when supplied; leave null when absent.",
    },
    "calculate_commute": {
        "origin_address": "The supplied starting address or named location. For an apartment-search follow-up, a returned apartment ID is a valid simulated starting-location reference; do not invent a street address.",
        "destination_address": "The supplied destination address or named location. A label such as 'my office' or 'the university' is valid for this simulated API; no extra street-address clarification is needed for a supplied label.",
        "mode": "The requested transport mode, such as driving, walking or transit; use the default only if unstated.",
    },
    "update_search_filter": {
        "filter_name": "One search-filter key the user asked to update. A filter update needs neither city nor an apartment search. Use separate calls for separate requested keys.",
        "value": "The final value for this filter. Preserve numeric values as numbers and boolean constraints as booleans; preserve genuinely named neighborhood labels.",
    },
    "track_order": {
        "order_id": "The full requested order identifier. Join separately spelled letters/digits. Do not introduce dashes, spaces or punctuation unless the user requested those separators. Do not drop repeated digits.",
    },
    "search_products": {
        "query": "The user-requested product category or search phrase, retaining meaningful descriptors. Do not invent a brand or product ID.",
        "max_price": "The user-stated maximum budget as a number, or null if no budget was stated.",
    },
    "add_to_cart": {
        "product_id": "The exact product ID supplied by the user or returned by the prior product search. Do not add separators or substitute a product name.",
        "quantity": "The final requested unit count. Use one only if no quantity was supplied; retain corrections and complete each requested cart action once.",
    },
}


class BenchmarkTools:
    def __init__(self, upstream: Path = UPSTREAM, *, latency_profile: str = "instant"):
        checkout = upstream.resolve()
        source = checkout / "v3"
        if not (source / "mock_apis.py").is_file():
            raise FileNotFoundError("Run python scripts/setup_fdb.py to fetch the pinned FDB-v3 source")
        actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        if actual != REVISION:
            raise ValueError("FDB-v3 source is not at the pinned revision")
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
        registry_type = importlib.import_module("mock_apis").MockAPIRegistry
        if set(registry_type.FUNCTIONS) != set(CONTRACTS):
            raise ValueError("Pinned FDB-v3 tool registry differs from the advertised twelve contracts")
        self.registry = registry_type(latency_profile=latency_profile)

    def definitions(self) -> list[ToolDefinition]:
        definitions = []
        for name, (write, properties, optional) in CONTRACTS.items():
            described = {key: {**spec, "description": FIELD_GUIDANCE[name][key]}
                         for key, spec in properties.items()}
            schema = {
                "type": "object", "properties": described,
                "required": [key for key in properties if key not in optional],
                "additionalProperties": False,
            }
            def invoke(*, _name=name, **kwargs):
                if _name == "search_apartments":
                    kwargs.setdefault("bedrooms", 1)
                    kwargs.setdefault("max_price", 2000.0)
                    kwargs.pop("pets_allowed", None)
                elif _name == "search_products":
                    kwargs.pop("category", None)
                return self.registry.call(_name, **kwargs)
            definitions.append(ToolDefinition(name, write, schema, invoke, blocking=True))
        return definitions
