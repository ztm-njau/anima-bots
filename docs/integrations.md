# Working with the rest of the ecosystem

This page moved: everything about plugins, MCP (both directions), AstrBot plugins, the OneBot
bridge for NoneBot / Koishi / AstrBot, the OpenAI-compatible endpoint and the market is in
[plugins.md](plugins.md). Personas, character cards and persona packs are in [personas.md](personas.md).

## SillyTavern: world books and character cards

- 世界书 → 导入: a SillyTavern world book (`.json`) or a character card (`.png` / `.json`, V2 or V3);
  the card's character book becomes a book. A SillyTavern world book dropped into
  `bots/<name>/lorebook/` also works as-is.
- 人设 → 新建人设 → 角色卡 (or 世界书 → 用角色卡创建新 bot): the card becomes a new persona with
  persona, examples, world book and avatar, plus Anima's chat-platform rules.

## magpie and other gateways

See [providers.md](providers.md): magpie, OpenRouter, New API–style relays, Ollama and LM Studio all
plug into the 模型 panel.
