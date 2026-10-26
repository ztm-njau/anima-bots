# Audit: what an excellent bot needs, and where Anima stood (2026-10-26)

| Area | Before this pass | Gap | Done in this pass |
| --- | --- | --- | --- |
| Message debounce | ✅ per-chat batching, max wait | – | – |
| Human pacing, sleep, mood, daily life | ✅ | – | – |
| Model providers | ✅ 18 presets, panel, routing, backups, magpie | – | – |
| Owner control | ❌ nobody is "the owner" | can't manage her from chat | owner list + chat commands (`/拉黑` `/放行` `/静音` `/好友` …) |
| Refusing chats | ❌ | trolls can drain her and the budget | blocklist, per-group mute, and she can end a chat herself (`end_chat` skill, timed) |
| Friend / group requests | ⚠️ accept-all switch only | no rules, no review, no delete | rules (accept / smart / ask owner / ignore), pending list with approve/reject, delete friend, leave group |
| 世界书 (lorebook) | ❌ | no keyword-triggered lore | lorebook with keys, constant entries, priority, budget; **imports SillyTavern world books and character cards** (PNG/JSON, V2/V3) |
| 表情包 | ⚠️ text emotes + empty meme folders | no real sticker images | sticker library with tags; she sends them by mood; collects stickers people send and tags them with vision; console upload |
| Image understanding | ⚠️ live only | forgotten next turn; non-vision models blind | every image gets a short caption stored in memory, so later turns and any model know what it was |
| Long-term memory | ⚠️ facts by person | no topical recall | automatic recall of related facts and past moments each turn (character-bigram BM25, works for Chinese without extra models) |
| 用户画像 | ⚠️ scattered facts | no summary of who someone is | per-person profile (who they are, how to treat them) kept current by reflection, editable |
| Plugins / ecosystem | ⚠️ Python skills only | can't reuse GitHub tools | **MCP client**: any MCP server (Claude Desktop `mcpServers` format) becomes her tools |
| One place to manage | ⚠️ playground + model page | settings spread over files | unified console: 聊天 · 模型 · 用户 · 世界书 · 表情包 · 插件 · 设置 |
| Safety in demo mode | ⚠️ | canned lines could reach real QQ friends | real platforms stay silent until a real model is connected |
