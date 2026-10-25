# Working in this repo

Anima is a Python engine for human-like social bots; each bot is a folder under `bots/`
(Claudette / 可乐 is the first). It runs on the owner's Mac, not in the cloud.

## Commands

- Python is uv-managed 3.12. Never use the system `python3` (3.9). `uv sync --all-extras` installs everything.
- Tests: `uv run pytest` (fast, offline: `FakeLLM` + a recorder adapter, pacing off). Lint: `uv run ruff check src tests`.
- Try changes: `uv run anima play` (web playground on :8765, `--demo` without an API key, `--fast` to skip pacing),
  `uv run anima chat` (terminal), `uv run anima doctor`.

## Map

- `src/anima/core/brain.py` is the heart: perceive → debounce → `policy.py` → pacing → `compose()` → `deliver()`.
- Prompt: `core/prompt.py`. Stable system prompt = `persona.md` + `examples.md` + protocol; the per-turn scene goes in a
  trailing mid-conversation system message so the cached prefix survives. Keep it that way.
- The model's output protocol (one line per bubble, `[sticker:x]`, `[poke]`, `[voice]…[/voice]`, `[mood:x]`, `[silent]`)
  is parsed in `core/markup.py`; if you add a tag, document it in `PROTOCOL` in `prompt.py`.
- Claude calls: `llm/anthropic_provider.py`. Default model `claude-opus-5-5`, `output_config.effort`, no
  temperature/top_p (rejected by the API), `fallbacks: "default"` behind the `server-side-fallback-2026-07-01` beta.
- Platforms: `adapters/`. Only `send()` is required; capabilities (`typing`, `poke`, `voice`, ...) are optional.
- Skills: `skills/` with the `@skill` decorator; bot-specific ones in `bots/<name>/skills/*.py`.

## Rules of the house

- Her life runs on `identity.timezone` (Beijing), not the Mac's timezone. Use `brain.clock`, never `datetime.now()`.
- Secrets only in `.env` (gitignored) and `data/<bot>/secrets/`. Never print or commit them.
- She never claims to be human when sincerely asked. Don't weaken that in prompts.
- She speaks only in QQ groups listed in `bot.toml`; keep group opt-in.
- Platform actions that publish (posting, sending to real accounts) need the owner's go-ahead before you run them live.
