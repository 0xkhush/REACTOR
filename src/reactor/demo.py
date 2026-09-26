"""Scripted control-layer demonstration, not speech recognition or a benchmark run."""

import asyncio
import json
from dataclasses import asdict

from reactor.controller import Controller
from reactor.state import Proposal
from reactor.tools.timers import TimerService


async def run_demo() -> dict:
    timers = TimerService()
    controller = Controller("offline-kitchen", timers.definitions())
    try:
        original = await controller.resolve_input(
            await controller.begin_input(), mode="new", changes={"name": "pasta", "duration_seconds": 600},
        )
        corrected = await controller.resolve_input(
            await controller.begin_input(), mode="correction", changes={"duration_seconds": 420},
        )
        obsolete = await controller.execute(Proposal(
            original, "start-pasta", "create_timer", {"name": "pasta", "duration_seconds": 600},
        ))
        proposal = Proposal(corrected, "start-pasta", "create_timer", {"name": "pasta", "duration_seconds": 420})
        created, duplicate = await asyncio.gather(controller.execute(proposal), controller.execute(proposal))
        cancel_request = await controller.resolve_input(await controller.begin_input(), mode="new")
        cancelled = await controller.execute(Proposal(
            cancel_request, "cancel-pasta", "cancel_timer", {"timer_id": created.result["timer_id"]},
        ))
        listing = (await timers.list_timers())["timers"]
        if (obsolete.status != "cancelled_before_dispatch"
                or created.operation_id != duplicate.operation_id
                or len(listing) != 1
                or listing[0]["duration_seconds"] != 420
                or cancelled.result["state"] != "cancelled"):
            raise RuntimeError("offline demonstration invariants failed")
        return {
            "mode": "scripted_offline",
            "obsolete_proposal": asdict(obsolete),
            "create_operation_id": created.operation_id,
            "created_timer": created.result,
            "duplicate_operation_id": duplicate.operation_id,
            "cancellation": cancelled.result,
            "timers": listing,
            "snapshot": controller.snapshot(),
        }
    finally:
        await controller.close()
        await timers.close()


def main() -> None:
    print(json.dumps(asyncio.run(run_demo()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
