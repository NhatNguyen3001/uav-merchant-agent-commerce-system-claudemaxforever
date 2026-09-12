from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

# Override with MACS_MODEL. Opus 5 is the default: about 30 s per run with the forced-tool wrapper and no schema
# slips in testing. Haiku 4.5 is about 6 s faster but built over-budget bundles and slipped on the schema once in three runs.
MODEL_ID = os.environ.get("MACS_MODEL", "claude-opus-5")
FIXTURES = Path(__file__).with_name("fixtures")
T = TypeVar("T", bound=BaseModel)


class LLMOutputError(Exception):
    pass


def strict_schema(model_cls: Type[BaseModel]) -> dict:
    """JSON schema for strict tool use: every object closed (additionalProperties false) with all keys required."""
    schema = model_cls.model_json_schema()

    def close(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for v in node.values():
                close(v)
        elif isinstance(node, list):
            for v in node:
                close(v)

    close(schema)
    return schema


class LLM:
    def __init__(self, fake: bool, fixtures_dir: Path | None = None) -> None:
        self.fake = fake
        self._fixtures = fixtures_dir or FIXTURES
        self._client = None

    @classmethod
    def from_env(cls) -> "LLM":
        return cls(fake=os.environ.get("FAKE_LLM", "0") == "1")

    async def structured(self, model_cls: Type[T], system: str, user: str, fixture: str,
                         tool_result_id: str | None = None) -> T:
        if self.fake:
            raw = json.loads((self._fixtures / f"{fixture}.json").read_text(encoding="utf-8"))
            if tool_result_id is not None:
                raw = json.loads(json.dumps(raw).replace('"tool_result_id": "T"', f'"tool_result_id": "{tool_result_id}"'))
            try:
                return model_cls.model_validate(raw)
            except ValidationError as e:
                raise LLMOutputError(str(e)) from e
        return await self._real(model_cls, system, user)

    async def _real(self, model_cls: Type[T], system: str, user: str) -> T:
        import anthropic
        if self._client is None:
            self._client = anthropic.AsyncAnthropic()
        last_err: Exception | None = None
        messages = [{"role": "user", "content": user}]
        for attempt in range(3):
            try:
                # A non-strict forced tool call generates about 2.5x faster than structured outputs or strict
                # tools (both use constrained decoding) for this nested schema. Pydantic validates afterwards;
                # a validation failure is fed back to the model once.
                tool_name = "record_" + model_cls.__name__.lower()
                kwargs = dict(
                    model=MODEL_ID, max_tokens=4000, system=system,
                    messages=messages,
                    tools=[{"name": tool_name, "description": f"Record the {model_cls.__name__}.",
                            "input_schema": model_cls.model_json_schema()}],
                    tool_choice={"type": "tool", "name": tool_name},
                )
                if "haiku" not in MODEL_ID:
                    kwargs["output_config"] = {"effort": "low"}  # effort is not accepted on Haiku 4.5
                resp = await self._client.messages.create(**kwargs)
                if resp.stop_reason == "refusal":
                    raise LLMOutputError("model refused the request")
                block = next((b for b in resp.content if b.type == "tool_use"), None)
                if block is None:
                    raise LLMOutputError(f"no tool call in response (stop_reason={resp.stop_reason})")
                try:
                    return model_cls.model_validate(block.input)
                except ValidationError as e:
                    if attempt >= 1:
                        raise LLMOutputError(str(e)) from e
                    last_err = e
                    messages = messages + [
                        {"role": "assistant", "content": resp.content},
                        {"role": "user", "content": [
                            {"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                             "content": f"Input did not match the schema:\n{e}\nCall {tool_name} again with corrected input."},
                        ]},
                    ]
                    continue
            except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
                last_err = e
                await asyncio.sleep(1.5)
        raise LLMOutputError(f"anthropic call failed: {last_err}")
