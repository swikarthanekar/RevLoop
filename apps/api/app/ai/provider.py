"""LLM provider protocol and test doubles (Prompt 17)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    async def generate_structured(
        self,
        *,
        task: str,
        input: BaseModel,
        output_schema: type[T],
    ) -> T: ...


PreGenerateHook = Callable[[str, BaseModel], None]


class FakeLLMProvider:
    """Deterministic in-memory provider for tests."""

    def __init__(
        self,
        *,
        response: BaseModel | None = None,
        error: Exception | None = None,
        pre_generate: PreGenerateHook | None = None,
    ) -> None:
        self._response = response
        self._error = error
        self.pre_generate = pre_generate
        self.call_count = 0
        self.last_task: str | None = None
        self.last_input: BaseModel | None = None

    async def generate_structured(
        self,
        *,
        task: str,
        input: BaseModel,
        output_schema: type[T],
    ) -> T:
        self.call_count += 1
        self.last_task = task
        self.last_input = input
        if self.pre_generate is not None:
            self.pre_generate(task, input)
        if self._error is not None:
            raise self._error
        if self._response is None:
            raise RuntimeError("FakeLLMProvider response not configured.")
        if not isinstance(self._response, output_schema):
            raise TypeError(
                f"Fake response type {type(self._response)!r} "
                f"does not match {output_schema!r}."
            )
        return self._response


class CallableLLMProvider:
    """Provider backed by an async callable for adversarial tests."""

    def __init__(
        self,
        handler: Callable[[str, BaseModel, type[T]], Awaitable[T]],
    ) -> None:
        self._handler = handler
        self.call_count = 0

    async def generate_structured(
        self,
        *,
        task: str,
        input: BaseModel,
        output_schema: type[T],
    ) -> T:
        self.call_count += 1
        return await self._handler(task, input, output_schema)
