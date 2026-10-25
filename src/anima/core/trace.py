"""A tiny pub/sub for the brain's inner monologue (decisions, tool calls, costs).

The playground subscribes to it so you can watch her think; logs get a copy too.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from loguru import logger


class TraceBus:
    def __init__(self, keep: int = 300):
        self.history: deque[dict[str, Any]] = deque(maxlen=keep)
        self.subscribers: set[asyncio.Queue] = set()

    def emit(self, kind: str, /, **data: Any) -> None:
        event = {"kind": kind, "ts": time.time(), **data}
        self.history.append(event)
        logger.debug("trace {} {}", kind, {k: v for k, v in data.items() if k != "prompt"})
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.discard(queue)
