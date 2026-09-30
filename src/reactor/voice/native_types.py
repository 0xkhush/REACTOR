"""Strict JSON numbers for SDKs that discard Annotated validation metadata."""

from pydantic_core import core_schema


class JsonNumber(float):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.union_schema([
            core_schema.int_schema(strict=True), core_schema.float_schema(strict=True),
        ])

    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):
        return {"type": "number"}


class JsonInteger(int):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.int_schema(strict=True)
