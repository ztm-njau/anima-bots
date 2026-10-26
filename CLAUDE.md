# Working in this repo

Anima is a Python engine for human-like social bots; each bot is a folder under `bots/`
(Claudette / 可乐 is the first). It runs on the owner's Mac, not in the cloud.

## Commands

- Python is uv-managed 3.12. Never use the system `python3` (3.9). `uv sync` installs everything. `anima` in ~/.local/bin is a wrapper (scripts/install-shortcut.sh) so the CLI works from any folder.
- Tests: `uv run pytest` (fast, offline: `FakeLLM` + a recorder adapter, pacing off). Lint: `uv run ruff check src tests`.
- Try changes: `uv run anima play` (web playground on :8765, `--demo` without an API key, `--fast` to skip pacing),
  `uv run anima chat` (terminal), `uv run anima doctor`.

## Map

- `src/anima/core/brain.py` is the heart: perceive → debounce → `policy.py` → pacing → `compose()` → `deliver()`.
- Prompt: `core/prompt.py`. Stable system prompt = `persona.md` + `examples.md` + protocol; the per-turn scene goes in a
  trailing mid-conversation system message so the cached prefix survives. Keep it that way.
- The model's output protocol (one line per bubble, `[sticker:x]`, `[poke]`, `[voice]…[/voice]`, `[mood:x]`, `[silent]`)
  is parsed in `core/markup.py`; if you add a tag, document it in `PROTOCOL` in `prompt.py`.
- Models: `llm/catalog.py` (presets, prices) → `llm/registry.py` (data/providers.json, env detection, per-bot
  data/<bot>/routing.json) → `make_provider()` builds a `RoutedLLM` (chat / background / backups). Default brain is
  DeepSeek `deepseek-flash` via `llm/openai_compat.py` (thinking disabled, temperature 1.3). The panel is
  `web/providers.py` + `web/static/providers.html`; it swaps `brain.llm` live.
- Claude calls: `llm/anthropic_provider.py`. `output_config.effort`, no temperature/top_p (rejected by the API),
  `fallbacks: "default"` behind the `server-side-fallback-2026-07-01` beta.
- `anima eval` / the panel's 考考她 run `evals.py` scenarios on scratch memory; use them before and after prompt changes.
- Platforms: `adapters/`. Only `send()` is required; capabilities (`typing`, `poke`, `voice`, ...) are optional.
- Skills: `skills/` with the `@skill` decorator; bot-specific ones in `bots/<name>/skills/*.py`.

## Rules of the house

- Her life runs on `identity.timezone` (Beijing), not the Mac's timezone. Use `brain.clock`, never `datetime.now()`.
- Secrets only in `.env`, `data/providers.json` and `data/<bot>/secrets/` (all gitignored). Never print or commit
  them, never send a key to the browser, and don't read other apps' credential files.
- Tests must not touch real `data/`: point `anima.config.DATA_DIR` at tmp_path.
- She never claims to be human when sincerely asked. Don't weaken that in prompts.
- She speaks only in QQ groups listed in `bot.toml`; keep group opt-in.
- Platform actions that publish (posting, sending to real accounts) need the owner's go-ahead before you run them live.
