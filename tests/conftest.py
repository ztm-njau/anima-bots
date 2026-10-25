from __future__ import annotations

import asyncio
import random

import pytest

from anima.adapters.base import Adapter
from anima.config import load_bot
from anima.core.brain import Brain
from anima.core.clock import Clock
from anima.core.events import Bubble, Chat, Incoming
from anima.core.memory import Memory
from anima.llm.fake import FakeLLM
from anima.web import wake_offset


class Recorder(Adapter):
    """Captures everything the brain sends."""

    platform = "playground"
    capabilities = frozenset({"poke", "typing", "read"})

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[tuple[str, str, str | None]] = []
        self.bubbles: list[Bubble] = []
        self.pokes: list[str] = []
        self.reads = 0

    async def send(self, chat: Chat, bubble: Bubble, quote: str | None = None) -> str | None:
        self.sent.append((chat.key, bubble.source, quote))
        self.bubbles.append(bubble)
        return f"m{len(self.sent)}"

    async def poke(self, chat: Chat, user_id: str) -> None:
        self.pokes.append(user_id)

    async def mark_read(self, chat: Chat, ev: Incoming) -> None:
        self.reads += 1


@pytest.fixture
def bot():
    return load_bot("claudette")


@pytest.fixture
async def memory():
    mem = await Memory(":memory:").open()
    yield mem
    await mem.close()


@pytest.fixture
def make_brain(bot, memory):
    """Build a brain with a scripted model, instant pacing, and the clock at 20:00 Beijing time."""

    def build(responder=None, side=None, hour: int = 20, adapter: Adapter | None = None, seed: int = 7):
        clock = Clock(bot.config.identity.timezone)
        clock.set_offset_hours(wake_offset(clock, hour))
        brain = Brain(bot, memory, FakeLLM(responder, side), clock=clock, rng=random.Random(seed))
        brain.humanizer.scale = 0.0
        recorder = adapter or Recorder()
        brain.attach(recorder)
        recorder.brain = brain
        return brain, recorder

    return build


async def wait_idle(brain: Brain, limit: float = 3.0) -> None:
    """Wait until every chat session has finished processing."""
    deadline = asyncio.get_running_loop().time() + limit
    await asyncio.sleep(0.08)
    while asyncio.get_running_loop().time() < deadline:
        busy = any(s.busy or s.buffer or (s.timer and not s.timer.done()) for s in brain.sessions.values())
        if not busy:
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("brain did not go idle")
