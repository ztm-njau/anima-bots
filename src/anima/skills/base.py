"""Skills are tools the model can call mid-conversation. Each one is a small async function.

Register with ``@skill(...)``. Built-ins live in this package; a bot can add its own in
``bots/<name>/skills/*.py`` and they register the same way.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from anima.core.events import Chat, Incoming, Sender
from anima.llm.base import ToolSpec

if TYPE_CHECKING:
    from anima.core.brain import Brain


@dataclass
class SkillContext:
    brain: Brain
    chat: Chat
    sender: Sender | None
    batch: list[Incoming] = field(default_factory=list)

    @property
    def memory(self):
        return self.brain.memory

    @property
    def clock(self):
        return self.brain.clock

    @property
    def user_key(self) -> str:
        return self.sender.user_key(self.chat.platform) if self.sender else "unknown"


Handler = Callable[[SkillContext, dict[str, Any]], Awaitable[str | dict | list]]


@dataclass
class Skill:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler
    platforms: tuple[str, ...] | None = None

    def available_on(self, platform: str) -> bool:
        return self.platforms is None or platform in self.platforms

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.parameters)


REGISTRY: dict[str, Skill] = {}
BUILTIN = ["memory_tools", "fun", "games", "weather", "reminders", "bilibili_tools", "life_tools"]


def skill(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
    platforms: list[str] | None = None,
):
    def decorator(fn: Handler) -> Handler:
        params = {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
            "additionalProperties": False,
        }
        REGISTRY[name] = Skill(name, description, params, fn, tuple(platforms) if platforms else None)
        return fn

    return decorator


def load_builtin() -> None:
    for module in BUILTIN:
        importlib.import_module(f"anima.skills.{module}")


def load_bot_skills(bot_dir: Path) -> None:
    for path in sorted((bot_dir / "skills").glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"anima_bot_skills.{bot_dir.name}.{path.stem}", path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            logger.info("Loaded bot skill module {}", path.name)


def select(patterns: list[str], bot_dir: Path | None = None) -> list[Skill]:
    """``["*"]`` = everything; ``["*", "-weather"]`` = everything but weather; or list names."""
    load_builtin()
    if bot_dir:
        load_bot_skills(bot_dir)
    chosen: set[str] = set()
    for pattern in patterns:
        if pattern == "*":
            chosen |= set(REGISTRY)
        elif pattern.startswith("-"):
            chosen.discard(pattern[1:])
        elif pattern in REGISTRY:
            chosen.add(pattern)
        else:
            logger.warning("Unknown skill {!r} in bot.toml", pattern)
    return [s for name, s in REGISTRY.items() if name in chosen]


async def run_skill(skill_: Skill, ctx: SkillContext, args: dict[str, Any]) -> str:
    try:
        out = await skill_.handler(ctx, args)
    except Exception as exc:  # a broken tool should never break the conversation
        logger.exception("Skill {} failed", skill_.name)
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
    return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
