from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

MODEL_ID = "claude-opus-5"
FIXTURES = Path(__file__).with_name("fixtures")
T = TypeVar("T", bound=BaseModel)


class LLMOutputError(Exception):
    pass


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
        for attempt in range(2):
            try:
                resp = await self._client.messages.parse(
                    model=MODEL_ID,
                    max_tokens=8000,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    output_format=model_cls,
                    output_config={"effort": "low"},
                )
                if resp.stop_reason == "refusal" or resp.parsed_output is None:
                    raise LLMOutputError(f"no structured output (stop_reason={resp.stop_reason})")
                return resp.parsed_output
            except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
                last_err = e
                await asyncio.sleep(1.5)
            except ValidationError as e:
                raise LLMOutputError(str(e)) from e
        raise LLMOutputError(f"anthropic call failed after retry: {last_err}")
