# 参与贡献 · Contributing

欢迎一起让 Anima 更像一个"人"。下面是上手方式和这个仓库的几条规矩。
Thanks for helping Anima feel more like someone. How to get started, and the house rules, below.

## 开发环境 · Setup

```bash
git clone https://github.com/ztm-njau/anima-bots && cd anima-bots
uv sync                       # Python 3.12, all dependencies and dev tools
uv run pytest                 # offline tests: a scripted model, no network, no real accounts
uv run ruff check src tests   # lint
uv run anima play --demo      # the web playground on :8765 without any API key
```

需要 [uv](https://docs.astral.sh/uv/)。QQ / magpie 相关功能另需 Docker（Docker Desktop 或 OrbStack）。
Needs [uv](https://docs.astral.sh/uv/); the QQ and magpie integrations also need Docker.

## 代码地图 · Where things are

`CLAUDE.md` 和 `docs/architecture.md` 有完整的地图。最常改的地方：
See `CLAUDE.md` and `docs/architecture.md`. The usual places:

| 想做的事 · You want to… | 去这里 · Go to |
| --- | --- |
| 新的内置技能 · a built-in skill | `src/anima/skills/`（`@skill` 装饰器）；可选功能更适合做成插件 |
| 新的平台 · a platform | `src/anima/adapters/`（只需实现 `send()`）, register in `runtime.py` |
| 新的模型提供商预设 · a provider preset | `src/anima/llm/catalog.py` |
| 新的人设 · a persona | 后台「人设」或 `uv run anima new <name>`，见 `docs/personas.md` |
| 插件 · a plugin | `plugins/<id>/plugin.toml` + `main.py`（`anima.plugin`），见 `docs/plugins.md` |
| 插件市场条目 · a market entry | `market/index.json` |
| 兼容层 · compatibility layers | `src/anima/compat/astrbot.py`, `src/anima/adapters/onebot_bridge.py` |
| 网页 · web UI | `src/anima/web/static/`（中文为源文本，英文写在 `i18n.js` 的 `EN` 里） |

## 规矩 · House rules

- **她不冒充真人。** 被认真问到时，她承认自己是 AI 驱动的虚拟角色。不要在提示词里削弱这一点。
  **She never claims to be human** when sincerely asked. Don't weaken that in prompts.
- **不提交密钥。** 只放在 `.env`、`data/providers.json`、`data/<bot>/secrets/`（都已忽略）。测试不能碰真实的
  `data/`，用 `tmp_path` 并改 `anima.config.DATA_DIR`。
  **No secrets in git**, and tests never touch the real `data/` folder.
- **她的时间是北京时间**：用 `brain.clock`，不要 `datetime.now()`。
  **Her clock is Beijing time**: use `brain.clock`.
- **群聊默认不发言**：只在 `bot.toml` 列出的群说话。
  **Groups are opt-in.**
- **网页都要有 中 / EN 切换**：脚本里的文字走 `t("…")`，并在 `EN` 里补英文。她自己说的话不翻译。
  **Every page keeps the 中 / EN toggle**; never translate her own words.
- **界面克制**：山水的色调和留白，不堆特效。
  **Keep the UI quiet**: ink-and-paper palette, whitespace, few effects.
- 改了提示词或人设，跑一下 `uv run anima eval`（考考她）看前后差别。
  After prompt or persona changes, compare `uv run anima eval` before and after.

## 提交与 PR · Commits and pull requests

1. 从 `main` 开一个分支，一个 PR 只做一件事。One change per PR, branched from `main`.
2. 确保 `uv run pytest` 和 `uv run ruff check src tests` 通过，新行为配上测试。Tests and lint pass; new behaviour has tests.
3. 提交信息说清楚"为什么"。用中文或英文都可以。Commit messages explain why; Chinese or English is fine.
4. 涉及界面的改动请附截图。UI changes come with a screenshot.

发现安全问题请不要开公开 issue，见 [SECURITY.md](SECURITY.md)。
Security issues go through [SECURITY.md](SECURITY.md), not public issues.

参与本项目即表示你同意遵守 [行为准则](CODE_OF_CONDUCT.md)。
By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
