import asyncio
import threading

import pytest
from jsonschema.exceptions import SchemaError, ValidationError

from reactor.tools.base import ToolDefinition


SCHEMA = {
    "type": "object", "properties": {"n": {"type": "integer"}},
    "required": ["n"], "additionalProperties": False,
}


async def increment(n):
    return {"n": n + 1}


async def test_async_tool_validates_and_invokes():
    tool = ToolDefinition("increment", False, SCHEMA, increment)
    assert await tool.invoke({"n": 6}) == {"n": 7}
    with pytest.raises(ValidationError):
        await tool.invoke({"n": "6"})
    with pytest.raises(ValidationError):
        await tool.invoke({"n": 6, "extra": True})


async def test_blocking_tool_runs_off_event_loop():
    main_thread = threading.get_ident()

    def handler(n):
        return {"n": n, "thread": threading.get_ident()}

    tool = ToolDefinition("thread", False, SCHEMA, handler, blocking=True)
    result = await asyncio.wait_for(tool.invoke({"n": 7}), 2)
    assert result["thread"] != main_thread


def test_handler_mode_must_match_declared_contract():
    with pytest.raises(ValueError, match="async"):
        ToolDefinition("wrong", False, SCHEMA, lambda n: n)
    with pytest.raises(ValueError, match="synchronous"):
        ToolDefinition("wrong", False, SCHEMA, increment, blocking=True)
    with pytest.raises(SchemaError):
        ToolDefinition("wrong", False, {"type": "not-a-type"}, increment)


async def test_tool_arguments_are_copied_before_handler_mutation():
    async def mutate(items):
        items.append("changed")
        return items

    schema = {"type": "object", "properties": {"items": {"type": "array"}}}
    tool = ToolDefinition("mutate", False, schema, mutate)
    args = {"items": ["original"]}
    assert await tool.invoke(args) == ["original", "changed"]
    assert args == {"items": ["original"]}
