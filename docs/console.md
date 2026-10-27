# The console and her relationships

Open http://127.0.0.1:8765/console (or the 🗂 管理后台 badge in the playground). Everything
here is also in files you can edit by hand; the console just saves you the trip.

| Page | What it does |
| --- | --- |
| 概览 | Model status, people, pending requests, 世界书, 表情包, plugins at a glance |
| 人设 | The persona gallery: switch live, try one on the current model, edit persona / examples / names, duplicate, export a pack, retire; create from a form, a one-line idea drafted by the model, a SillyTavern card or a pack ([personas.md](personas.md)) |
| 用户与画像 | Everyone she knows: profile (用户画像), nickname, affinity, what she remembers (add / delete), block, let her talk to someone again, forget a person entirely |
| 好友请求 | Friend requests and group invites waiting for you, and what was decided |
| 世界书 | Keyword-triggered lore, editable; import SillyTavern world books or a character card's book; test which entries a sentence triggers; turn a character card into a new bot |
| 表情包 | Her sticker images: starter pack, ones she collected, uploads; edit tags |
| 扩展 | Installed plugins (on/off, settings, dependencies, uninstall), the market (Anima, MCP + the official registry, AstrBot, NoneBot, persona packs), MCP servers, and interop: the OneBot bridge, `/mcp`, `/v1` ([plugins.md](plugins.md)) |
| 设置 | Owners, how chatty she is, interests, rhythm (debounce, bubbles, group manners), per-group tuning, image memory, recall, diary, QQ groups and request rules, other platforms, and the active persona's text |

## Owner commands (in any chat with her)

Set `owners = ["qq:你的QQ号"]` in `bot.toml` (or 设置). The playground and terminal always count
as the owner. Commands are answered directly, never by the model.

```
/状态                     her state, model, spend, pending requests
/拉黑 QQ号或@人  /放行 QQ号  blocked people are invisible to her
/静音  /解除静音             in this group she only listens
/请求  /同意 编号  /拒绝 编号   friend requests and group invites
/删好友 QQ号  /退群 群号
/画像 QQ号或@人  /忘掉 QQ号
```

## Friend requests and group invites

`[platforms.qq] friend_requests` / `group_invites`:

- `accept`: yes to everyone (after a human-ish delay).
- `smart` (default for friends): yes to people she already knows from groups, or whose note contains
  one of `friend_keywords`; everyone else waits for you, and you get a DM about it.
- `owner` (default for invites): always ask you.
- `ignore`: leave them.

When she accepts someone, she greets them a minute or two later, referring to their note.

## She can walk away

If someone keeps insulting or pushing her past her limits, she can stop replying to them for a
while (`end_chat`, 5 minutes to a day), the way a person would. You can undo it in 用户与画像.

## 表情包

She sends `[meme:关键词]` when a sticker says it better than words. Sources:

- `bots/<name>/memes/<标签>/*.png`: packs (the folder name is the tag; she ships with 16 of her own,
  redraw them with `scripts/make_starter_stickers.py`).
- Stickers people send in chats: with a vision model she saves some (`collect_stickers`, default 50%)
  and tags them by what they mean ("狗头 无语 嫌弃").
- Uploads in the console.

## Memory

- Every image is described once and the description stays in the chat history, so later turns and
  models without vision know what was sent.
- Each turn she may "suddenly remember" related facts about other people and old moments of this
  chat (`recall`), shown in the playground's 内心独白 under the scene.
- Reflection keeps a short 用户画像 per person and updates it as she learns more.
