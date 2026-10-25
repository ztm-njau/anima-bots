# Anima · 可乐

A soul engine for human-like social bots, and its first resident: **Claudette (可乐)**, a curious,
sharp-tongued, warm-hearted girl who lives on the internet and hangs out on QQ, Bilibili, WeChat
and Douyin.

![The playground: chat on the left, her inner world on the right](docs/playground.jpg)

## What makes her feel like someone

- **Rhythm.** She waits for you to finish typing (three quick messages become one batch), takes
  a believable moment to notice, marks it read, then types bubble by bubble at phone speed.
- **A life.** She runs on Beijing time: up around 08:30, online classes in the morning, most
  chatty in the evening, asleep after midnight (later on weekends, with the odd sleepless night).
  Messages sent while she sleeps are answered when she wakes, with a groggy "刚醒".
- **A day of her own.** Every morning she plans a small day (a theme, a few events, a song, what
  her electronic cat Bug got up to). Every night she writes a diary, optionally posted to Bilibili.
- **Mood.** A small emotional state that drifts back to her cheerful baseline and colours her tone.
- **Memory.** People (facts, nicknames, birthdays, how close she feels), her own invented details
  (so her stories stay consistent), and a collection of beautiful sentences strangers said to her.
  A background reflection pass distils each conversation into memories.
- **Group sense.** Always answers an @, her name, a reply, or a poke. Otherwise she chimes in now
  and then, more when the topic is stars, cats, films or late-night food, less when she has been
  talking a lot. Knowing when to stay quiet is most of the trick.
- **Native everywhere.** One sticker vocabulary rendered as QQ faces, Bilibili emotes and WeChat
  emoji; voice notes on QQ (neural TTS); pokes back when poked; "对方正在输入…"; quote replies.
- **Honest.** She is openly an AI-driven character and never claims to be human when sincerely
  asked, which also matches China's labelling rules for AI-generated content.

## Skills

Tools she reaches for mid-conversation, in her own voice: remember / recall / nicknames /
birthdays, daily fortune (stable per person per day), tarot, dice, choosing for the indecisive,
"可乐签", games with hidden state (guess the number, 海龟汤 turtle soup, 成语接龙), weather
(Open-Meteo), reminders she actually delivers, Bilibili video lookups (title, stats, AI summary)
for links people share, her own day and treasure box, and Claude's web search for fresh facts.

## Platforms

| Platform | How | State |
| --- | --- | --- |
| Playground | Local web UI with time travel, simulated group chat, live view of her mood and reasoning | ready |
| Terminal | `anima chat` | ready |
| QQ | NapCat in Docker (OrbStack) → OneBot v11 WebSocket. Groups are opt-in. | ready, needs a QQ account scan |
| Bilibili | DMs, replies and @-mentions, live-room danmaku, dynamics | ready, needs a QR login |
| WeChat | Official account (公众号) webhook; or any OneBot v11 WeChat bridge | ready, needs an account and a public URL |
| Douyin | A real Chrome window in live rooms | experimental |

Step-by-step guides: [QQ](docs/platforms/qq.md) · [Bilibili](docs/platforms/bilibili.md) ·
[WeChat](docs/platforms/wechat.md) · [Douyin](docs/platforms/douyin.md)

## Quick start

```bash
cp .env.example .env          # then put your ANTHROPIC_API_KEY in it
uv run anima play             # http://127.0.0.1:8765
```

Without a key she runs in demo mode (canned lines), which is still enough to explore the UI.
Her brain defaults to Claude Opus 5.5 at low effort for chat, with prompt caching and the
server-side refusal fallback. Any OpenAI-compatible model (DeepSeek, Qwen, LM Studio) also
works: see `[llm]` in `bots/claudette/bot.toml`.

```bash
uv run anima doctor           # what's ready, what's missing, how to fix it
uv run anima chat             # talk in the terminal
uv run anima napcat up        # start QQ (scan the QR code in the WebUI)
uv run anima login bilibili   # QR login for Bilibili
uv run anima run              # every platform enabled in bot.toml
uv run anima memory           # who she knows and what she remembers
uv run anima diary            # read her diary
uv run anima service install  # keep her running in the background (launchd)
```

## Layout

```
bots/
  claudette/         persona.md, examples.md, bot.toml, life.toml, stickers.toml, guard.toml
  _template/         `uv run anima new <name>` copies this to start another bot
src/anima/
  core/              brain, policy, humanizer, schedule, mood, memory, reflection, life, prompt
  llm/               Claude (Anthropic SDK), OpenAI-compatible, and a scripted fake for tests
  skills/            the tools above; bots can add their own in bots/<name>/skills/*.py
  adapters/          playground, console, onebot (QQ), bilibili, wechat, douyin
  web/               playground UI and webhooks
infra/napcat/        Docker compose + OneBot config template for QQ
data/<bot>/          memory.db, logs, voice cache, cookies and browser profiles (gitignored)
```

A bot is a folder: everything that makes Claudette *Claudette* is text you can edit. Another
character is `uv run anima new luna`, a persona, and a `bot.toml`.

## Accounts and safety

- Give each bot its own platform accounts. Automating a personal account can break a platform's
  terms and get it restricted; built-in rate limits and human pacing reduce that risk, they don't
  remove it.
- She only speaks in QQ groups you list. Secrets live in `.env` and `data/`, both gitignored.
- `guard.toml` is a last-line output filter for topics that get accounts restricted on Chinese
  platforms; the persona already steers away from them.

See [docs/architecture.md](docs/architecture.md) for how the brain works.
