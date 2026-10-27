"""Anima as an MCP server: the running persona becomes tools for Claude Code, Cursor, Cherry Studio…

Served at ``http://127.0.0.1:8765/mcp`` (Streamable HTTP) whenever the web server runs, and it
always talks to whichever persona is active, so switching personas needs no reconfiguration::

    claude mcp add --transport http anima http://127.0.0.1:8765/mcp

Only this computer may connect, unless ``ANIMA_API_KEY`` is set and sent as a Bearer token.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from anima.core.events import Chat, Sender
from anima.core.recall import bm25, terms

if TYPE_CHECKING:
    from starlette.applications import Starlette

    from anima.runtime import Runtime


def build_mcp_app(runtime: Runtime) -> Starlette:
    from mcp.server.mcpserver import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings

    server = MCPServer(
        "anima",
        title="Anima",
        instructions="Talk to the active Anima persona, read who she is, search what she remembers and read her diary.",
    )

    @server.tool(description="Send a message to the active persona and get her reply (one line per chat bubble). "
                             "Each conversation id is its own chat in her memory.")
    async def chat(message: str, user_name: str = "MCP", conversation: str = "default") -> str:
        brain = runtime.brain
        conv = "".join(ch for ch in conversation if ch.isalnum() or ch in "-_")[:48] or "default"
        lines = await brain.answer(Chat("mcp", "private", conv, user_name), Sender(f"mcp-{conv}", user_name[:24] or "MCP"),
                                   message, reason="有人通过 MCP 工具跟你说话")
        return "\n".join(lines) or "（她没有说话）"

    @server.tool(description="Who the active persona is: name, aliases, tagline, persona text.")
    async def persona() -> str:
        bot = runtime.bot
        ident = bot.config.identity
        return json.dumps({"key": bot.key, "name": ident.display_name, "aliases": ident.aliases,
                           "tagline": ident.tagline, "persona": bot.read("persona.md")[:4000]}, ensure_ascii=False)

    @server.tool(description="Search what the active persona remembers (facts about people and herself).")
    async def recall(query: str, limit: int = 8) -> str:
        memory = runtime.brain.memory
        facts = await memory.all_facts(500)
        if not facts:
            return "[]"
        scores = bm25(terms(query) or [query], [terms(f.content) for f in facts])
        ranked = [f for score, f in sorted(zip(scores, facts, strict=True), key=lambda x: -x[0]) if score > 0]
        return json.dumps([{"about": f.subject, "fact": f.content} for f in ranked[: max(1, min(limit, 30))]],
                          ensure_ascii=False)

    @server.tool(description="The active persona's recent diary entries, newest first.")
    async def diary(days: int = 3) -> str:
        entries = await runtime.brain.memory.journal_list("diary", max(1, min(days, 14)))
        return json.dumps(entries, ensure_ascii=False)

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]", "[::1]:*",
                       "host.docker.internal", "host.docker.internal:*"],
        allowed_origins=["http://127.0.0.1", "http://127.0.0.1:*", "http://localhost", "http://localhost:*"],
    )
    return server.streamable_http_app(streamable_http_path="/mcp", transport_security=security)
