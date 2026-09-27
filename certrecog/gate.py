from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from certrecog.errors import BusyError, MAX_WAITING

T = TypeVar("T")


class Gate:
    """同时只跑一个识别请求。正在跑的不算名额，后面最多再等 max_waiting 个。"""

    def __init__(self, max_waiting: int = MAX_WAITING) -> None:
        self.max_waiting = max_waiting
        self._meta = asyncio.Lock()
        self._work = asyncio.Lock()
        self.waiting = 0

    async def run(self, fn: Callable[[], Awaitable[T]]) -> T:
        async with self._meta:
            if self.waiting >= self.max_waiting:
                raise BusyError()
            self.waiting += 1
        entered = False
        try:
            async with self._work:
                async with self._meta:
                    self.waiting -= 1
                    entered = True
                return await fn()
        finally:
            if not entered:
                async with self._meta:
                    self.waiting -= 1
