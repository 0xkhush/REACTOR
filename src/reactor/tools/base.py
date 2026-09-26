"""Schema-validated async boundary for local or blocking tools."""

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from jsonschema import Draft202012Validator

from reactor.state import copy_json


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    state_modifying: bool
    schema: dict[str, Any]
    handler: Callable[..., Any]
    blocking: bool = False
    _validator: Draft202012Validator = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        schema = copy_json(self.schema)
        Draft202012Validator.check_schema(schema)
        asynchronous = inspect.iscoroutinefunction(self.handler)
        if self.blocking and asynchronous:
            raise ValueError("blocking tools need a synchronous handler")
        if not self.blocking and not asynchronous:
            raise ValueError("non-blocking tools need an async handler")
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "_validator", Draft202012Validator(copy_json(schema)))

    def validate(self, args: dict[str, Any]) -> dict[str, Any]:
        detached = copy_json(args)
        if not isinstance(detached, dict):
            raise ValueError("tool arguments must be an object")
        self._validator.validate(detached)
        return detached

    async def invoke(self, args: dict[str, Any]) -> Any:
        validated = self.validate(args)
        if self.blocking:
            return await asyncio.to_thread(self.handler, **validated)
        return await self.handler(**validated)
