"""Own callback tasks and observe sanitized failures instead of losing exceptions."""

import asyncio


class EventTasks:
    def __init__(self, trace):
        self.trace = trace
        self.pending = set()
        self.errors = []

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.pending.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task):
        self.pending.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self.errors.append(type(error).__name__)
            try:
                self.trace.event("voice_event_error", error_type=type(error).__name__)
            except Exception as recording_error:
                self.errors.append(type(recording_error).__name__)

    async def drain(self):
        while self.pending:
            await asyncio.gather(*list(self.pending), return_exceptions=True)
