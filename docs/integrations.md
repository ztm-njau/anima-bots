# Working with the rest of the ecosystem

## MCP plugins (tools from GitHub)

`bots/<name>/mcp.json` uses the same `mcpServers` format as Claude Desktop and Cursor, so a server's
README snippet can be pasted into 插件 in the console or into the file:

```json
{"mcpServers": {
  "time": {"command": "uvx", "args": ["mcp-server-time", "--local-timezone=Asia/Shanghai"]},
  "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
  "howtocook": {"command": "npx", "args": ["-y", "howtocook-mcp"]},
  "remote": {"url": "https://example.com/mcp"}
}}
```

Each server starts with the bot; its tools become hers as `<server>__<tool>`. stderr goes to
`data/<bot>/logs/plugin-<server>.log`. `uvx` and `npx` are already on this Mac.

## SillyTavern: world books and character cards

- 世界书 → 导入: a SillyTavern world book (`.json`) or a character card (`.png` / `.json`, V2 or V3);
  the card's character book becomes a book. A SillyTavern world book dropped into
  `bots/<name>/lorebook/` also works as-is.
- 世界书 → 用角色卡创建新 bot: the card becomes `bots/<slug>/` with persona, examples, world book and
  avatar, plus Anima's chat-platform rules. Run it with `uv run anima play <slug>`.

## Claudette as a model for other bot frameworks (AstrBot, NoneBot, Koishi, SillyTavern…)

Anima serves an OpenAI-compatible endpoint whenever the web server runs:

- Base URL `http://127.0.0.1:8765/v1` (from Docker on this Mac: `http://host.docker.internal:8765/v1`)
- Model `claudette` (the bot's folder name)
- Key: set `ANIMA_API_KEY=…` in `.env` and use it; without it only this computer may call.

Each caller (the request's `user` field, or the first message) is its own conversation in her
memory, with persona, 世界书, recall and tools. Her bubbles come back as lines. This is how
AstrBot can use her as its brain while keeping its own
plugin market: add an OpenAI provider in AstrBot with the values above.

## magpie and other gateways

See [providers.md](providers.md): magpie, OpenRouter, New API–style relays, Ollama and LM Studio all
plug into the 模型 panel.
