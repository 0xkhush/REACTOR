"""Adversarial Generalization, Counterfactual, and Mutation Test Suite.

Tests whether REACTOR architecture relies on benchmark vocabulary or hardcoded answers,
or generalizes to completely novel, out-of-distribution values and dynamic corrections.
"""

import asyncio
import json
import pytest
from reactor.controller import Controller
from reactor.tools.base import ToolDefinition
from reactor.voice.turns import TurnBridge
from reactor.voice.arguments import normalize_argument_values
from reactor.voice.grounding import ground_request_arguments


async def run_adversarial_suite():
    print("=" * 60)
    print("ADVERSARIAL GENERALIZATION & COUNTERFACTUAL SUITE")
    print("=" * 60)

    # 1. Test novel out-of-distribution values (Reykjavík, Nov 17, ZX-9182, etc.)
    executed_tools = []
    def dummy_invoke(**kwargs):
        executed_tools.append(kwargs)
        return {"status": "ok", "echo": kwargs}

    definitions = [
        ToolDefinition("search_flights", False, {
            "type": "object",
            "properties": {"destination": {"type": "string"}, "date": {"type": "string"}},
            "required": ["destination", "date"]
        }, dummy_invoke, blocking=True),
        ToolDefinition("book_flight", True, {
            "type": "object",
            "properties": {"passenger_name": {"type": "string"}},
            "required": ["passenger_name"]
        }, dummy_invoke, blocking=True),
        ToolDefinition("track_order", False, {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"]
        }, dummy_invoke, blocking=True)
    ]

    controller = Controller("test-adv-session", definitions)
    bridge = TurnBridge(controller)

    print("\n--- Test 1: Novel OOD Values (Reykjavik, 17 November, ZX-9182) ---")
    req1 = await bridge.resolve("Book a flight to Reykjavík on 17 November", mode="new")
    await bridge.execute("search_flights", {"destination": "Reykjavík", "date": "17 November"}, "call-1", request=req1)
    
    assert len(executed_tools) == 1
    assert executed_tools[0]["destination"] == "Reykjavík"
    assert executed_tools[0]["date"] == "17 November"
    print("PASS: OOD Flight search preserved:", executed_tools[0])

    print("\n--- Test 2: Multi-step Correction Cascade (Tokyo -> Seoul -> Singapore) ---")
    executed_tools.clear()
    req_t = await bridge.resolve("Book a flight to Tokyo tomorrow", mode="new")
    # User corrects to Seoul
    req_s = await bridge.resolve("Actually, make that Seoul", mode="correction")
    # User corrects again to Singapore
    req_sg = await bridge.resolve("No wait, I meant Singapore", mode="correction")
    
    # Provider tries to execute Tokyo on stale revision
    try:
        await bridge.execute("search_flights", {"destination": "Tokyo", "date": "tomorrow"}, "call-tokyo", request=req_t)
        tokyo_executed = True
    except Exception as e:
        tokyo_executed = False

    # Provider executes Singapore on final revision
    await bridge.execute("search_flights", {"destination": "Singapore", "date": "tomorrow"}, "call-sg", request=req_sg)
    
    print(f"Stale Tokyo execution attempted: executed={tokyo_executed}")
    print(f"Active calls executed: {executed_tools}")
    assert len(executed_tools) == 1
    assert executed_tools[0]["destination"] == "Singapore"
    print("PASS: Controller correctly superseded stale intents Tokyo -> Seoul and only executed Singapore!")

    print("\n--- Test 3: Novel Spelled Identifier with hyphenated ASR ---")
    # Spoken: "order Z-X-9-1-8-2" -> model proposed "Z-X-9-1-8-2"
    transcript = "My order ID is Z-X-9-1-8-2 please track it"
    norm_id = ground_request_arguments("track_order", {"order_id": "Z-X-9-1-8-2"}, transcript)
    print(f"Spelled identifier 'Z-X-9-1-8-2' with transcript evidence -> '{norm_id['order_id']}'")
    assert norm_id["order_id"] == "ZX9182"
    print("PASS: Spelled identifier correctly compacted to ZX9182!")

    print("\n--- Test 4: Compound Business ID Protection (Explicit Dash Preservation) ---")
    # If transcript has "RQ dash 78" or "RQ-78"
    transcript_dash = "The reference is RQ dash 78"
    norm_dash = ground_request_arguments("track_order", {"order_id": "RQ-78"}, transcript_dash)
    print(f"Preserved compound dash ID with explicit 'dash' -> '{norm_dash['order_id']}'")
    assert norm_dash["order_id"] == "RQ-78"
    print("PASS: Compound dash preserved when explicit dash was spoken!")

    print("\n--- Test 5: Counterfactual Slot Mutation Matrix ---")
    mutations = [
        {"slot": "destination", "orig": "Mumbai", "mut": "Delhi", "tool": "search_flights", "args": {"destination": "Delhi", "date": "August 10"}},
        {"slot": "date", "orig": "Friday", "mut": "Monday", "tool": "search_flights", "args": {"destination": "Boston", "date": "Monday"}},
        {"slot": "quantity", "orig": "1", "mut": "4", "tool": "add_to_cart", "args": {"product_id": "P52", "quantity": "4"}},
        {"slot": "currency", "orig": "EUR", "mut": "GBP", "tool": "get_exchange_rate", "args": {"amount": "100", "from_currency": "USD", "to_currency": "GBP"}},
        {"slot": "budget", "orig": "$1500", "mut": "$3200", "tool": "search_apartments", "args": {"city": "Chicago", "max_price": "$3,200"}},
        {"slot": "account", "orig": "checking", "mut": "savings", "tool": "modify_autopay", "args": {"bill_type": "water", "source_account": "savings account"}},
    ]

    results_table = []
    for m in mutations:
        out = normalize_argument_values(m["tool"], m["args"])
        # Check that mutated value is present in normalized output
        val_str = str(list(out.values()))
        changed = m["orig"] not in val_str and (m["mut"].lower() in val_str.lower() or str(m["mut"]).replace("$", "").replace(",", "") in val_str)
        results_table.append({
            "slot": m["slot"],
            "original": m["orig"],
            "mutated": m["mut"],
            "output": out,
            "status": "PASS" if changed else "FAIL"
        })

    print(f"{'Slot':<12} | {'Original':<10} | {'Mutated':<12} | {'Status':<6}")
    print("-" * 50)
    for r in results_table:
        print(f"{r['slot']:<12} | {r['original']:<10} | {r['mutated']:<12} | {r['status']:<6}")
        assert r["status"] == "PASS"

    await controller.close()
    await bridge.close()
    print("\nALL ADVERSARIAL & COUNTERFACTUAL GENERALIZATION CHECKS PASSED!")


if __name__ == "__main__":
    asyncio.run(run_adversarial_suite())
