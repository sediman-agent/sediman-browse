from __future__ import annotations

import asyncio
from typing import Any


class InterruptSignal:
    _instance: InterruptSignal | None = None

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._reason: str = ""
        self._partial_result: dict[str, Any] | None = None

    @classmethod
    def get(cls) -> InterruptSignal:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def trigger(self, reason: str = "Interrupted by user") -> None:
        self._reason = reason
        self._event.set()

    def clear(self) -> None:
        self._event.clear()
        self._reason = ""
        self._partial_result = None

    def is_set(self) -> bool:
        return self._event.is_set()

    def reason(self) -> str:
        return self._reason

    def set_partial_result(self, result: dict[str, Any]) -> None:
        self._partial_result = result

    def get_partial_result(self) -> dict[str, Any] | None:
        return self._partial_result

    def check(self) -> None:
        if self._event.is_set():
            raise InterruptedError(self._reason)

    async def wait(self) -> None:
        await self._event.wait()
        raise InterruptedError(self._reason)


class InterruptedError(Exception):
    pass
