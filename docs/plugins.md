# Plugins, MCP and the rest of the ecosystem · 插件与生态

Anima can borrow abilities from five places. They all show up in the console under **扩展**
(Extensions), and a persona turns them on for herself.

| Where it comes from | How it runs | Compatibility |
| --- | --- | --- |
| **Anima plugins** (`plugins/`, `data/plugins/`) | inside Anima | full: tools, hooks, commands, timers |
| **MCP servers** (any from GitHub or the official MCP Registry) | as child processes or remote URLs | full: every tool becomes hers |
| **AstrBot plugins** (~1,300 in the community collection) | inside Anima, on a compatibility layer | partial: see below |
| **NoneBot2 / Koishi / AstrBot / Yunzai…** (whole frameworks) | next to Anima, through the OneBot bridge | full, because nothing is translated |
| **SillyTavern** character cards and world books | imported as personas and 世界书 | full for the formats |

And the other way round, Anima is usable *by* other software: an MCP server at `/mcp` and an
OpenAI-compatible endpoint at `/v1`.

## Anima plugins

A plugin is a folder with a manifest and an entry file:

```
plugins/hello/
  plugin.toml
  main.py
```

```toml
# plugin.toml
id = "hello"
name = "打招呼"
version = "1.0.0"
description = "一个示例插件"
author = "you"
license = "MIT"
homepage = "https://github.com/you/anima-hello"
entry = "main.py"                  # default
requirements = ["httpx>=0.27"]     # optional; the console has an 安装依赖 button
permissions = ["network"]          # informational, shown before install

[config]                           # settings the owner edits in the console
greeting = { type = "string", default = "你好", label = "开场白" }
loud = { type = "boolean", default = false, label = "大声一点" }
```

```python
# main.py
from anima.plugin import Plugin

plugin = Plugin()


@plugin.skill("say_hello", "跟某人打招呼", {"name": {"type": "string"}}, required=["name"])
async def say_hello(ctx, args):
    # ctx.config, ctx.data_dir (her own folder for this plugin), ctx.chat, ctx.sender, ctx.memory, ctx.clock
    return f"{ctx.config['greeting']}，{args['name']}"


@plugin.command("hello", help="打个招呼", aliases=["hi"])
async def hello(ctx, ev, arg):
    return f"{ctx.config['greeting']} {ev.sender.name}"   # sent as-is, no model call


@plugin.on_message
async def filter_spam(ctx, ev):
    if "加群领红包" in ev.text:
        return False                 # she never sees it


@plugin.on_scene
async def today(ctx, chat, batch):
    return "今天是插件节"             # a note in her picture of the moment


@plugin.on_reply
async def sign(ctx, chat, reply):
    pass                             # adjust reply.bubbles before they are sent


@plugin.every(3600)
async def hourly(ctx):
    await ctx.speak("qq:group:123456", "整点了，随口提醒大家喝水")   # in her own words
    # or ctx.send(chat, "exact text", image=path) to send something as-is
```

Hooks run with a time limit; an exception is logged and the conversation carries on. Three
plugins ship as examples: `hitokoto` (a tool and a command that call a public API),
`keyword-reply` (fixed answers without a model call) and `countdown` (per-chat storage and a scene
note).

Turn one on in the console, with `uv run anima plugin enable hitokoto`, or in her bot.toml:

```toml
plugins = ["hitokoto", "countdown"]

[plugin_config.hitokoto]
categories = "d,i"
```

Install from GitHub (an Anima or AstrBot plugin repository, a subfolder via `/tree/<branch>/<dir>`,
or any zip link): console → 扩展 → 从地址或文件安装, or `uv run anima plugin install <url>`. Installed
plugins live in `data/plugins/<id>` and uninstall to `data/trash`. **A plugin is code running on your
computer**; the console asks before every install.

## AstrBot plugins

AstrBot plugins (a folder with `main.py` and `metadata.yaml`) load directly. Anima provides the
parts of `astrbot.api` that plugins use most:

| AstrBot | In Anima |
| --- | --- |
| `@register`, `Star`, `initialize()`, `terminate()` | loaded and started with the persona |
| `@filter.command("x")`, `command_group` | `/x args`; typed arguments (`a: int`) are parsed |
| `@filter.event_message_type(...)`, `@filter.regex(...)` | run on incoming messages; `event.stop_event()` hides the message from her |
| `@filter.llm_tool(name=...)` | becomes one of her tools; the schema comes from the docstring `Args:` |
| `@filter.on_llm_request()` | text added to `req.system_prompt` reaches her scene |
| `@filter.permission_type(ADMIN)` | owner only (`owners` in bot.toml) |
| `event.plain_result / image_result / chain_result`, `Plain`, `Image`, `At` | sent as-is |
| `yield event.request_llm(prompt=...)` | she answers in character with that prompt as the cue |
| `self.context.get_using_provider().text_chat(...)` | her background model |
| `self.context.send_message(umo, chain)`, `AstrBotConfig`, `_conf_schema.json` | supported |

Not emulated: `event.bot.api.call_action` and other platform internals, AstrBot's database and
web dashboard. A plugin that needs them fails to load with a message saying what is missing,
rather than half-working. Plugins that list `requirements.txt` get an 安装依赖 button.

## MCP servers

`bots/<name>/mcp.json` uses the same `mcpServers` shape as Claude Desktop and Cursor, so a server's
README snippet pastes in as-is (console → 扩展 → MCP 服务器):

```json
{"mcpServers": {
  "time": {"command": "uvx", "args": ["mcp-server-time", "--local-timezone=Asia/Shanghai"]},
  "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
  "amap": {"command": "npx", "args": ["-y", "@amap/amap-maps-mcp-server"], "env": {"AMAP_MAPS_API_KEY": "…"}},
  "remote": {"url": "https://example.com/mcp"}
}}
```

Each server starts with the persona; its tools become hers as `<server>__<tool>`. The market's
MCP shelf has a curated list and searches the official
[MCP Registry](https://registry.modelcontextprotocol.io) live; servers that need keys ask for them.
`uvx` servers need [uv](https://docs.astral.sh/uv/), `npx` servers need Node.js.

## The OneBot bridge: NoneBot, Koishi, AstrBot side by side

Most QQ bot frameworks speak OneBot v11. With the bridge on, Anima passes every NapCat event to
them and their API calls back, so their entire plugin ecosystems run unchanged on the same QQ
account:

```toml
[platforms.qq]
bridge_listen = 3010                          # NoneBot / Koishi connect here (forward WebSocket)
bridge_connect = ["ws://127.0.0.1:6199/ws"]   # or Anima connects to them (reverse WebSocket, AstrBot)
bridge_prefixes = ["/", "#"]                  # these messages are theirs; she remembers but doesn't answer
# bridge_token_env = "ONEBOT_BRIDGE_TOKEN"    # optional access token, read from .env
```

- **NoneBot2**: `.env` → `ONEBOT_WS_URLS=["ws://127.0.0.1:3010"]` (OneBot V11 adapter), then
  `nb plugin install …` as usual.
- **Koishi**: adapter-onebot, protocol `ws`, endpoint `ws://127.0.0.1:3010`.
- **AstrBot**: platform aiocqhttp (reverse WebSocket, port 6199 by default), and put its address in
  `bridge_connect`.

Her own owner commands and Anima plugin commands still go first. What the frameworks send through
her account goes into her memory as hers, so she isn't surprised by it later.

## Anima as an MCP server

Whenever the web server runs, `http://127.0.0.1:8765/mcp` (Streamable HTTP) offers four tools on
the *active* persona: `chat`, `persona`, `recall` (search her memories) and `diary`.

```bash
claude mcp add --transport http anima http://127.0.0.1:8765/mcp
```

Cursor / Cherry Studio and others: `{"mcpServers": {"anima": {"url": "http://127.0.0.1:8765/mcp"}}}`.
Only this computer may connect unless `ANIMA_API_KEY` is set and sent as a Bearer token.

## Anima as an OpenAI-compatible model

- Base URL `http://127.0.0.1:8765/v1` (from a Docker container on the same computer: `http://host.docker.internal:8765/v1`)
- Model: the persona's folder name, e.g. `claudette`
- Key: set `ANIMA_API_KEY=…` in `.env` and use it; without it only this computer may call.

Each caller is its own conversation in her memory, with persona, 世界书, recall and tools.

## The market

The console's 市场 (Market) reads five shelves: Anima plugins and persona packs from
[`market/index.json`](../market/index.json) (refreshed from GitHub), curated MCP servers plus the
MCP Registry, AstrBot's [plugin collection](https://github.com/AstrBotDevs/AstrBot_Plugins_Collection),
and NoneBot's [registry](https://registry.nonebot.dev/). Lists are cached for six hours in
`data/market/` and still work offline.

To list your plugin or persona pack, open a pull request adding it to `market/index.json` with a
public source and an honest description.
