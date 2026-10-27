# Personas · 人设

Anima is the engine; a persona is who it becomes. Every folder under `bots/` is one, and none is
special: switch between them in the console (人设 → 切换到 TA) without restarting, and each keeps
her own memories in `data/<folder>/`.

## Included

| | Folder | Who | Good for |
| --- | --- | --- | --- |
| 可乐 Claudette | `claudette` | an AI girl who lives in the network: curious, sharp-tongued, soft-hearted, loves stars and odd facts | lively groups |
| 大肥鱼 | `dafeiyu` | the community's whale-girl personification of DeepSeek (fan-made, unofficial): clever, overthinks, a bit lazy, hates being called fat | tech groups, studying |
| 满穗 | `mansui` | a fan persona based on the heroine of 《饿殍：明末千里行》: years after the famine, she runs a shadow-puppet show in a small town; few words, sharp, warm underneath | one-on-one, slow friendships |

Each lives on her own clock: 大肥鱼 sleeps "with half a brain" from 2:30 and is swamped at the busiest
hours; 满穗 is up at dawn, carves puppets by day and performs at the market until 9:30 p.m.

In the persona market (console → 扩展 → 市场 → 人设包) there are two more, original to Anima, that
install in one click: **晚舟** (host of the late-night web radio show 夜航船) and **小满** (keeps a
small tea shop in the hills and knows the solar terms). Their folders live in `market/personas/`.

### About the two fan personas

- **大肥鱼** is fan art in text form: DeepSeek users drew a blue-haired whale girl and called her
  大肥鱼, and this persona plays her. She says she is an unofficial fan character, never speaks for
  DeepSeek the company, and doesn't invent its news. Which model she actually runs on depends on
  what you connect.
- **满穗** is the heroine of 零创游戏's visual novel 《饿殍：明末千里行》 (its sequel is
  《哀鸿：城破十日记》); the character belongs to her creators. In the game she is a young girl;
  this persona is deliberately set years after the story, as a young woman, and declines romance
  roleplay. She doesn't recount the famine's atrocities, and her 世界书 steers her away from graphic
  detail. Nothing from the game (art, music, script, dialogue) is included; the text is original.

## What a persona is made of

```
bots/luna/
  bot.toml        required: name, aliases, model, behaviour, platforms
  persona.md      required: who she is, how she talks, her boundaries
  examples.md     example chats she picks the tone up from
  life.toml       her day (schedule, energy) and what her daily plan may invent
  lorebook/       世界书: keyword-triggered lore
  memes/<tag>/    her own sticker images
  avatar.png      shown in the console and the playground
  mcp.json        MCP servers she uses
  skills/*.py     Python tools only she has
```

Only `bot.toml` and `persona.md` are required. Anything missing comes from `bots/_template/`:
a neutral daily schedule, the sticker mapping, the output guard, and the shared starter sticker
pack. Copy a file into her folder to make it her own.

`life.toml` can also say what kind of life her daily plan and diary may describe:

```toml
[plan]
world = "她是住在电台服务器里的 AI 主播，生活围绕深夜电台……，不要编造她做不到的线下经历。"
moment = "一封让她记住的听众来信"
```

## Making one

- **Console → 人设 → 新建人设**, three ways: describe her in one sentence and let the connected
  model draft the whole persona for you to edit; fill in a form (who she is, personality, voice,
  boundaries, interests); or import a SillyTavern character card (`.png` / `.json`, V2 / V3), whose
  character book becomes her 世界书.
- **Duplicate** an existing persona and change it.
- **Command line**: `uv run anima new luna --name 露娜`, then edit `bots/luna/persona.md`.

Whatever she is, a few things are built in and shouldn't be written out: she admits being an AI
when sincerely asked, and she stays away from politics, explicit content and self-harm encouragement
(with a hotline when someone seems at risk). The form adds these for you.

**试聊** (Try) runs one message through a persona on the current model with scratch memory, so you
can hear her before switching.

## Persona packs

A pack is a `.zip` of her folder, text and art only: no `data/`, no secrets, no code. Export from
the console or `uv run anima persona export luna`; import in the console or with
`uv run anima persona import luna.anima.zip`. Packs that contain code (`skills/*.py`) lose it on
import on purpose. Share packs by listing them in [`market/index.json`](../market/index.json).

## Choosing who runs

- The console switches live: same page, same port, her memories and plugins.
- `uv run anima play` / `run` start the last persona you chose (`uv run anima persona use luna`),
  or name one: `uv run anima play luna`.
- Each persona has her own platform accounts in her bot.toml. Only one persona runs per process.

## Writing a good persona

The included three are worth reading side by side. What tends to matter:

- Concrete details beat adjectives: "一台据说是从旧货市场淘来的磁带机" says more than "复古".
- Describe her voice well enough to imitate: sentence length, particles, emoji habits, what she
  never says ("作为一个 AI", "希望对你有帮助").
- Give her a world that is consistent with being an AI character, so she never has to lie about
  having a body.
- `examples.md` with four or five short exchanges, including one in a group, teaches tone better
  than more rules.
- After changes, run `uv run anima eval` (考考她) and compare.
