# Third-party notices · 第三方声明

Anima's own code, docs, original persona files (可乐, 晚舟, 小满), bundled plugins and the starter sticker
pack are MIT licensed (see `LICENSE`). The two fan personas are explained under "Fan personas" below.
This file lists what Anima uses, talks to, or learned from, and under which terms.

Anima 自己的代码、文档、人设文件和自带表情包都以 MIT 协议发布。下面列出它用到、对接或借鉴的第三方项目及其协议。

## Python dependencies · Python 依赖

Installed by `uv sync` / `pip`, not copied into this repository.

| Package | License | Used for |
| --- | --- | --- |
| anthropic, openai | Apache-2.0 | Model APIs |
| httpx, websockets, uvicorn, python-dotenv | BSD-3-Clause | Networking, web server, `.env` |
| fastapi, pydantic, typer, rich, loguru, aiosqlite, mcp, tomlkit | MIT | Web API, config, CLI, logging, memory, MCP plugins, settings editor |
| playwright | Apache-2.0 | Douyin adapter (drives an installed Chrome) |
| wechatpy | MIT | WeChat official-account adapter |
| cryptography | Apache-2.0 OR BSD-3-Clause | WeChat message encryption |
| edge-tts | LGPL-3.0 | Voice notes |
| tzdata | Apache-2.0 | Time zones |
| **bilibili-api-python** | **GPL-3.0-or-later** | Bilibili adapter and video lookups |
| qrcode | BSD | Bilibili QR login |

**About bilibili-api-python (GPL-3.0-or-later).** It is not one of the package's declared
dependencies. It sits in the `bilibili` dependency group, which `uv sync` installs for local use, and
Anima imports it only inside the Bilibili adapter and the `bilibili_video` skill. Everything else
works without it. If you distribute Anima *together with* bilibili-api-python (for example in a
bundle or image), that combined distribution must follow the GPL-3.0.

**关于 bilibili-api-python（GPL-3.0-or-later）**：它不在本包声明的依赖里，而是放在 `bilibili` 依赖组中，
`uv sync` 会为本地使用安装它；只有 B 站适配器和 `bilibili_video` 技能会导入它，其他功能不需要它。
如果你把 Anima 和它打包在一起分发（比如做成镜像），这个组合分发需要遵循 GPL-3.0。

## Services and images Anima talks to · 对接的外部项目

Referenced by name in compose files or docs; not redistributed here. Each has its own license and terms.

- **NapCat** (`mlikiowa/napcat-docker`, github.com/NapNeko/NapCatQQ): OneBot v11 for QQ. Automating a
  QQ account may break Tencent's terms; use a dedicated account at your own risk.
- **magpie** (github.com/yetone/magpie, MIT): local model gateway, optional.
- **Ollama, LM Studio**, and the model providers in `src/anima/llm/catalog.py`: optional backends.
- **Open-Meteo** (open-meteo.com): weather data for the `weather` skill.
- **Microsoft Edge text-to-speech**, reached through edge-tts: voice notes.
- **MCP servers** you add (for example `mcp-server-time`, `mcp-server-fetch`, `howtocook-mcp`): run
  only if you add them; each under its own license. The market searches the official
  **MCP Registry** (registry.modelcontextprotocol.io) and lists servers by name only.
- **Plugins you install** from the market or a link (Anima plugins, AstrBot plugins): downloaded by you
  from their own repositories, each under its own license. The market reads the public plugin lists of
  **AstrBot** (github.com/AstrBotDevs/AstrBot_Plugins_Collection) and **NoneBot**
  (github.com/nonebot/registry) and links to each project.
- **hitokoto.cn**: the public API behind the bundled `hitokoto` plugin.
- **NoneBot2, Koishi, AstrBot, Yunzai** and other OneBot v11 frameworks: connect through the OneBot
  bridge if you run them; nothing of theirs is included.

## Formats and ideas · 兼容的格式与借鉴的思路

No code from these projects is included.

- **SillyTavern** (AGPL-3.0) world-info JSON and the community **Character Card** specs V2/V3:
  Anima reads these formats so world books and cards can be imported.
- **cc-switch** (github.com/farion1231/cc-switch, MIT): provider endpoints and model ids in
  `catalog.py` follow its public preset catalog (October 2026); the panel's preset gallery and
  one-click switching are inspired by it.
- **New API** (github.com/QuantumNous/new-api) and **Cherry Studio** (github.com/CherryHQ/cherry-studio):
  the connection test, model-list fetch and per-provider settings in the provider panel are inspired by them.
- **AstrBot** (github.com/AstrBotDevs/AstrBot, AGPL-3.0): `src/anima/compat/astrbot.py` provides
  the same plugin-facing names (`astrbot.api.star`, `filter.command`, `AstrMessageEvent`…) so that
  AstrBot plugins can run, written from the public plugin documentation. It contains no AstrBot code.
- **OneBot v11** (github.com/botuniverse/onebot-11): the protocol the QQ adapter and the bridge speak.
- **Model Context Protocol** (modelcontextprotocol.io): the plugin protocol for MCP servers, and the
  protocol of Anima's own `/mcp` endpoint.
- **Contributor Covenant** 2.1 (CC BY 4.0): `CODE_OF_CONDUCT.md` is adapted from it.

## Fan personas · 同人人设

- **大肥鱼** (`bots/dafeiyu/`) is a fan persona of the whale-girl personification that DeepSeek users
  drew and named. "DeepSeek" and its whale logo belong to 杭州深度求索人工智能基础技术研究有限公司
  (DeepSeek); this persona is unofficial, not endorsed by DeepSeek, uses no DeepSeek artwork, and its
  text says so to anyone who asks.
- **满穗** (`bots/mansui/`) is a fan persona of the heroine of 《饿殍：明末千里行》 (*The Hungry Lamb:
  Traveling in the Late Ming Dynasty*, developed by 零创游戏, published by 2P Games); its sequel is
  《哀鸿：城破十日记》. The character, story and world belong to their creators. The persona here is
  original fan-written text set years after the story: no game images, music, script or dialogue
  are included. If the rights holders object, it will be taken down.
- The persona text of both is released under the same MIT terms as the rest of this repository only
  as far as Anima's own writing goes; it grants no rights in the underlying characters.

**同人说明**：「大肥鱼」是网友创作的 DeepSeek 拟人形象的同人人设，DeepSeek 名称和鲸鱼标志归深度求索公司所有，本人设非官方、
未经其认可，也不使用其任何美术素材。「满穗」出自零创游戏开发、2P Games 发行的《饿殍：明末千里行》（续作《哀鸿：城破十日记》），
角色、故事和世界观归原作者所有；这里是爱好者写的原创文字，设定在故事结束多年以后，不含游戏的图像、音乐、剧本或台词。
如权利人有异议，我们会下架。

## Assets · 素材

- The 16 starter stickers in `bots/_template/memes/` (shared by every persona) are original drawings made by
  `scripts/make_starter_stickers.py` from plain shapes (MIT). Their captions are rendered with a
  system CJK font installed on the machine that runs the script.
- The landscape backgrounds in `src/anima/web/static/` are original SVGs (MIT).
- Screenshots in `docs/` show Anima's own interface.
