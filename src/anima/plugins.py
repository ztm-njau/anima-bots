"""Plugins from the MCP ecosystem: any Model Context Protocol server becomes her tools.

Config is ``bots/<name>/mcp.json`` in the same ``mcpServers`` shape Claude Desktop, Cursor and
most GitHub READMEs use, so a server's install snippet can be pasted as-is::

    {"mcpServers": {"time": {"command": "uvx", "args": ["mcp-server-time"]},
                    "recipes": {"command": "npx", "args": ["-y", "howtocook-mcp"]},
                    "remote": {"url": "https://example.com/mcp"}}}

Each server runs for the life of the bot; its tools register as skills named ``<server>__<tool>``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from anima.skills.base import Skill, SkillContext

if TYPE_CHECKING:
    from anima.core.brain import Brain

# Picked for a chat companion; all verified to exist on PyPI / npm (2026-10).
RECOMMENDED = [
    {"name": "time", "title": "时间与时区", "desc": "查任意城市现在几点、换算时区",
     "config": {"command": "uvx", "args": ["mcp-server-time", "--local-timezone=Asia/Shanghai"]},
     "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/time"},
    {"name": "fetch", "title": "读网页", "desc": "别人发来链接时，打开网页看看讲了什么",
     "config": {"command": "uvx", "args": ["mcp-server-fetch"]},
     "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch"},
    {"name": "howtocook", "title": "程序员做饭指南", "desc": "菜谱、今天吃什么，正适合她的「云干饭」",
     "config": {"command": "npx", "args": ["-y", "howtocook-mcp"]},
     "repo": "https://github.com/worryzyy/HowToCook-mcp"},
]

_NAME = re.compile(r"[^a-zA-Z0-9_-]+")


def _field(obj: Any, *names: str) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _safe(name: str) -> str:
    return _NAME.sub("_", name).strip("_")[:28] or "plugin"


@dataclass
class ServerState:
    name: str
    config: dict[str, Any]
    status: str = "stopped"  # stopped | starting | running | error | disabled
    error: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    session: Any = None
    task: asyncio.Task | None = None
    stop: asyncio.Event = field(default_factory=asyncio.Event)


class PluginManager:
    def __init__(self, brain: Brain):
        self.brain = brain
        self.path: Path = brain.bot.dir / "mcp.json"
        self.servers: dict[str, ServerState] = {}

    # ------------------------------------------------------------ config

    def load_config(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("mcpServers", {})
        except json.JSONDecodeError:
            logger.error("{} is not valid JSON", self.path)
            return {}

    def save_config(self, servers: dict[str, dict[str, Any]]) -> None:
        self.path.write_text(json.dumps({"mcpServers": servers}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        for name, cfg in self.load_config().items():
            await self.start_server(name, cfg)

    async def stop(self) -> None:
        for name in list(self.servers):
            await self.stop_server(name)

    async def start_server(self, name: str, cfg: dict[str, Any]) -> ServerState:
        await self.stop_server(name)
        state = ServerState(name, cfg)
        self.servers[name] = state
        if cfg.get("disabled"):
            state.status = "disabled"
            return state
        state.status = "starting"
        ready = asyncio.Event()
        state.task = asyncio.create_task(self._run(state, ready))
        try:
            await asyncio.wait_for(ready.wait(), timeout=float(cfg.get("startup_timeout", 90)))
        except TimeoutError:
            state.status, state.error = "error", "启动超时（第一次运行可能在下载依赖，稍后点重启）"
        return state

    async def stop_server(self, name: str) -> None:
        state = self.servers.pop(name, None)
        if not state:
            return
        self._unregister(state)
        state.stop.set()
        if state.task:
            try:
                await asyncio.wait_for(state.task, timeout=5)
            except (TimeoutError, asyncio.CancelledError, Exception):
                state.task.cancel()

    async def _run(self, state: ServerState, ready: asyncio.Event) -> None:
        from mcp import ClientSession

        try:
            async with AsyncExitStack() as stack:
                if state.config.get("url"):
                    from mcp.client.streamable_http import streamable_http_client

                    streams = await stack.enter_async_context(streamable_http_client(state.config["url"]))
                else:
                    from mcp.client.stdio import StdioServerParameters, stdio_client

                    command = state.config.get("command", "")
                    resolved = shutil.which(command) or command
                    env = {**os.environ, **{k: str(v) for k, v in (state.config.get("env") or {}).items()}}
                    params = StdioServerParameters(command=resolved, args=list(state.config.get("args") or []), env=env,
                                                   cwd=state.config.get("cwd"))
                    log_dir = self.brain.bot.data_dir / "logs"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    errlog = stack.enter_context((log_dir / f"plugin-{_safe(state.name)}.log").open("a", encoding="utf-8"))
                    streams = await stack.enter_async_context(stdio_client(params, errlog=errlog))
                read, write = streams[0], streams[1]
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                listed = await session.list_tools()
                state.session = session
                state.tools = [  # MCP SDK 2.x is snake_case; 1.x camelCase
                    {"name": t.name, "description": (t.description or "")[:400],
                     "schema": _field(t, "input_schema", "inputSchema") or {"type": "object", "properties": {}}}
                    for t in listed.tools
                ]
                self._register(state)
                state.status, state.error = "running", ""
                logger.info("[plugins] {} ready with {} tools", state.name, len(state.tools))
                ready.set()
                await state.stop.wait()
        except asyncio.CancelledError:
            pass
        except BaseException as exc:  # noqa: BLE001 - surface any startup failure in the console
            leaf = exc
            while isinstance(leaf, BaseExceptionGroup) and leaf.exceptions:
                leaf = leaf.exceptions[0]  # the real reason, not "unhandled errors in a TaskGroup"
            state.status, state.error = "error", f"{type(leaf).__name__}: {leaf}"[:300]
            logger.warning("[plugins] {} failed: {}", state.name, state.error)
        finally:
            self._unregister(state)
            if state.status == "running":
                state.status = "stopped"
            state.session = None
            ready.set()

    # ------------------------------------------------------------ skills

    def _skill_name(self, server: str, tool: str) -> str:
        return f"{_safe(server)}__{_safe(tool)}"[:64]

    def _register(self, state: ServerState) -> None:
        for tool in state.tools:
            name = self._skill_name(state.name, tool["name"])

            async def handler(ctx: SkillContext, args: dict, _state=state, _tool=tool["name"]) -> str:
                return await self.call(_state, _tool, args)

            schema = dict(tool["schema"])
            schema.setdefault("type", "object")
            schema.setdefault("properties", {})
            skill = Skill(name, f"[插件 {state.name}] {tool['description']}", schema, handler)
            self.brain.skills = [s for s in self.brain.skills if s.name != name] + [skill]

    def _unregister(self, state: ServerState) -> None:
        prefix = f"{_safe(state.name)}__"
        self.brain.skills = [s for s in self.brain.skills if not s.name.startswith(prefix)]

    async def call(self, state: ServerState, tool: str, args: dict[str, Any]) -> str:
        if state.session is None:
            return json.dumps({"error": f"插件 {state.name} 没在运行"}, ensure_ascii=False)
        result = await asyncio.wait_for(state.session.call_tool(tool, args), timeout=60)
        parts = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            parts.append(text if text is not None else f"[{getattr(block, 'type', 'content')}]")
        structured = _field(result, "structured_content", "structuredContent")
        text = "\n".join(parts) or json.dumps(structured or {}, ensure_ascii=False)
        if _field(result, "is_error", "isError"):
            text = f"[插件报错] {text}"
        return text[:6000]

    def status(self) -> list[dict[str, Any]]:
        configured = self.load_config()
        out = []
        for name, cfg in configured.items():
            state = self.servers.get(name)
            out.append({
                "name": name, "config": cfg,
                "status": state.status if state else ("disabled" if cfg.get("disabled") else "stopped"),
                "error": state.error if state else "",
                "tools": [{"name": t["name"], "skill": self._skill_name(name, t["name"]), "description": t["description"]}
                          for t in (state.tools if state else [])],
            })
        return out
