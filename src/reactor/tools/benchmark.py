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
    "search_apartments": (False, {"city": field("string"), "bedrooms": field("integer"),
                                  "max_price": field("number")}, ()),
    "calculate_commute": (False, {"origin_address": field("string"), "destination_address": field("string"),
                                  "mode": field("string", optional=True, default="driving")}, ("mode",)),
    # mock_apis.update_search_filter accepts Any: preserve scalar values instead
    # of copying lk_agent_tool's narrower string-only hint and losing JSON types.
    "update_search_filter": (True, {"filter_name": field("string"),
                                    "value": field(["string", "number", "boolean"])}, ()),
    "track_order": (False, {"order_id": field("string")}, ()),
    "search_products": (False, {"query": field("string"),
                                "max_price": field(["number", "null"], optional=True)}, ("max_price",)),
    "add_to_cart": (True, {"product_id": field("string"),
                           "quantity": field("integer", optional=True, default=1)}, ("quantity",)),
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
            schema = {
                "type": "object", "properties": properties,
                "required": [key for key in properties if key not in optional],
                "additionalProperties": False,
            }
            def invoke(*, _name=name, **kwargs):
                return self.registry.call(_name, **kwargs)
            definitions.append(ToolDefinition(name, write, schema, invoke, blocking=True))
        return definitions
