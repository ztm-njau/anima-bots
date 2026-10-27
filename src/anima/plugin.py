"""The plugin API: what a plugin folder imports to add tools, hooks, commands and timers.

A plugin is a folder with a ``plugin.toml`` manifest and a Python entry file::

    plugins/hello/
      plugin.toml     id = "hello", name, version, description, author, entry = "main.py", [config]
      main.py

    # main.py
    from anima.plugin import Plugin

    plugin = Plugin()

    @plugin.skill("say_hello", "跟某人打招呼", {"name": {"type": "string"}}, required=["name"])
    async def say_hello(ctx, args):
        return f"你好，{args['name']}"

    @plugin.command("hello", help="打个招呼")
    async def hello(ctx, ev, arg):
        return f"你好呀 {ev.sender.name}"

    @plugin.on_scene
    async def note(ctx, chat, batch):
        return "今天是插件节"           # goes into her picture of the moment

Hooks never break a conversation: each runs with a time limit and its errors are logged.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from anima.core.events import Bubble, Chat, Incoming, Reply, Segment
from anima.skills.base import Skill

if TYPE_CHECKING:
    from anima.core.brain import Brain

__all__ = ["Plugin", "PluginContext", "Command", "Bubble", "Chat", "Incoming", "Reply", "Segment"]


@dataclass(eq=False)
class Command:
    name: str
    handler: Callable[..., Awaitable[str | None]]
    help: str = ""
    aliases: tuple[str, ...] = ()
    owner_only: bool = False


@dataclass
class Timer:
    seconds: float
    handler: Callable[..., Awaitable[None]]


class PluginContext:
    """What a plugin's functions get as ``ctx``: her brain, its own settings and folder, and ways to talk."""

    def __init__(self, brain: Brain, plugin: Plugin, config: dict[str, Any], data_dir: Path):
        self.brain = brain
        self.plugin = plugin
        self.config = config
        self.data_dir = data_dir
        self.log = logger.bind(plugin=plugin.id)

    @property
    def memory(self):
        return self.brain.memory

    @property
    def clock(self):
        return self.brain.clock

    @property
    def persona(self) -> str:
        return self.brain.cfg.identity.display_name

    async def speak(self, chat: Chat | str, instruction: str) -> None:
        """Have her bring something up in her own words (a reminder, a pushed news item…)."""
        await self.brain.speak(_chat(chat), instruction)

    async def send(self, chat: Chat | str, text: str = "", image: str | Path | None = None) -> None:
        """Send exactly this, without her rewriting it (for command output, pictures, tables)."""
        segments = [Segment("text", text)] if text else []
        if image:
            segments.append(Segment("image", Path(image).name, str(image)))
        if segments:
            await self.brain.deliver(_chat(chat), Reply(bubbles=[Bubble(segments, source=text or "[图片]")]))


class ToolContext(PluginContext):
    """``ctx`` for a plugin's tools: the plugin's context plus the chat the tool was called from."""

    def __init__(self, base: PluginContext, skill_ctx):
        super().__init__(base.brain, base.plugin, base.config, base.data_dir)
        self.chat, self.sender, self.batch = skill_ctx.chat, skill_ctx.sender, skill_ctx.batch

    @property
    def user_key(self) -> str:
        return self.sender.user_key(self.chat.platform) if self.sender else "unknown"


def _chat(chat: Chat | str) -> Chat:
    if isinstance(chat, Chat):
        return chat
    platform, kind, chat_id = chat.split(":", 2)
    return Chat(platform, kind, chat_id)  # type: ignore[arg-type]


@dataclass
class Plugin:
    id: str = ""  # filled from plugin.toml when loaded
    skills: list[Skill] = field(default_factory=list)
    commands: dict[str, Command] = field(default_factory=dict)
    timers: list[Timer] = field(default_factory=list)
    hooks: dict[str, list[Callable]] = field(default_factory=lambda: {k: [] for k in
                                                                      ("message", "scene", "reply", "start", "stop")})
    manifest: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------ decorators

    def skill(self, name: str, description: str, properties: dict[str, Any] | None = None,
              required: list[str] | None = None, platforms: list[str] | None = None):
        """A tool she may call mid-conversation. ``handler(ctx, args) -> str | dict``."""
        def decorator(fn):
            params = {"type": "object", "properties": properties or {}, "required": required or [],
                      "additionalProperties": False}
            self.skills.append(Skill(name, description, params, fn, tuple(platforms) if platforms else None))
            return fn
        return decorator

    def command(self, name: str, help: str = "", aliases: tuple[str, ...] | list[str] = (), owner_only: bool = False):
        """``/name arg`` in any chat. ``handler(ctx, ev, arg) -> str | None``; the string is sent as-is."""
        def decorator(fn):
            cmd = Command(name, fn, help, tuple(aliases), owner_only)
            for key in (name, *aliases):
                self.commands[key] = cmd
            return fn
        return decorator

    def every(self, seconds: float):
        """Run ``handler(ctx)`` every ``seconds`` while the plugin is on."""
        def decorator(fn):
            self.timers.append(Timer(max(10.0, seconds), fn))
            return fn
        return decorator

    def on_message(self, fn):
        """``handler(ctx, ev) -> bool | None`` before she reads a message; ``False`` hides it from her."""
        self.hooks["message"].append(fn)
        return fn

    def on_scene(self, fn):
        """``handler(ctx, chat, batch) -> str | list[str] | None``: notes for her picture of the moment."""
        self.hooks["scene"].append(fn)
        return fn

    def on_reply(self, fn):
        """``handler(ctx, chat, reply) -> None`` after she writes a reply and before it is sent."""
        self.hooks["reply"].append(fn)
        return fn

    def on_start(self, fn):
        self.hooks["start"].append(fn)
        return fn

    def on_stop(self, fn):
        self.hooks["stop"].append(fn)
        return fn


async def call_safely(fn: Callable, *args, timeout: float = 20.0, label: str = "") -> Any:  # noqa: ASYNC109
    try:
        return await asyncio.wait_for(fn(*args), timeout=timeout)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - a plugin may fail; she keeps talking
        logger.warning("[plugin] {} failed: {}: {}", label or getattr(fn, "__name__", "hook"), type(exc).__name__, exc)
        return None
