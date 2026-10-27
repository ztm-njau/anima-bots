# Changelog · 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added · 新增
- 人设成为一等公民：后台「人设」页可以浏览、试聊、编辑、复制、导出导入人设包、一键切换（不用重启）；新建人设可以填表、
  一句话让模型起草或导入角色卡。新增两个原创人设：晚舟（深夜电台主播）和小满（山里茶铺姑娘）。
  Personas are first-class: a gallery with try, edit, duplicate, packs and live switching; create from a form,
  a one-line idea or a character card. Two new original personas, 晚舟 and 小满.
- 插件系统：`plugin.toml` + `anima.plugin` 接口（技能、消息/场景/回复钩子、命令、定时任务、设置项），自带一言、关键词回复、倒数日。
  A plugin system with tools, hooks, commands, timers and settings; three bundled plugins.
- 生态兼容：AstrBot 插件直接加载（兼容层），OneBot 桥接让 NoneBot / Koishi / AstrBot 共用 QQ 号，MCP 官方注册表搜索。
  AstrBot plugins on a compatibility layer, a OneBot bridge for NoneBot / Koishi / AstrBot, MCP Registry search.
- 插件市场：Anima 插件、MCP、AstrBot、NoneBot、人设包五个货架。A market with five shelves.
- Anima 自身作为 MCP 服务器（`/mcp`）。Anima as an MCP server at `/mcp`.
- 命令行 `anima persona …`、`anima plugin …`。CLI groups for personas and plugins.

### Changed · 改进
- 引擎不再写死任何人设：默认人设记在 `data/anima.json`，日程和日记提示词、表情包起手包、作息与过滤词都改为人设自带或共享默认。
  The engine no longer assumes a persona; schedules, diary prompts, stickers and guard files are per persona or shared.
- 防抖：根据最后一句有没有说完、对方的打字节奏来决定等多久；群里只有对她说话的人会让她多等。
  Debounce reads whether the last line is finished and follows the sender's rhythm; in groups only
  people talking to her extend the wait.
- 打字时对方补了一句，她会重写回复；发到一半被打断会停下，下一轮自然接上。撤回的消息不再回复。
  She rewrites a reply if you add something while she types, stops mid-reply when interrupted, and
  ignores recalled (撤回) messages.
- 分段发送：按句子切分，不切断链接、数字、引号、颜文字；一次回复的打字时间有上限。
  Bubbles split at sentence breaks without cutting links, numbers, quotes or kaomoji; one reply's
  typing time is capped.
- 群聊：区分叫她和「喝可乐」，接着跟刚聊过的人说，别人互相 @ 时不插嘴，每小时插话有上限，
  会跟着复读，话题过去时自动引用。后台可按群调整（安静 / 活跃、等待、气泡、备注）。
  Group chat: name calls vs. drinks, follow-ups with her partner, no butting into others'
  conversations, hourly cap, 复读, auto-quote, and per-group tuning in the console.

## [0.1.0] - 2026-10-27

First public release · 首次公开发布

### Added · 新增
- Anima engine: per-chat debounce, group-aware reply policy, human pacing, Beijing-time daily life,
  mood, diary, daily plan, reminders, long-term memory with reflection, recall and 用户画像.
- Claudette (可乐) persona with voice, examples, 世界书, stickers and boundaries; honest about being an AI.
- Platforms: web playground, terminal, QQ via NapCat (OneBot v11), Bilibili, WeChat official account
  and OneBot bridges, Douyin live rooms (experimental).
- 模型提供商 panel: 18 presets (DeepSeek default), live switching, backups, cost per currency,
  persona preview and the 考考她 exam; magpie gateway integration and Docker deployment.
- 管理后台: people and profiles, friend requests and group invites by rule, 世界书 with SillyTavern
  import, 表情包 library with an original starter pack, MCP plugins, settings editor.
- Owner commands, blocklist, per-group mute, and an `end_chat` skill so she can walk away.
- OpenAI-compatible `/v1` endpoint so other bot frameworks can use her brain.
- 中 / EN toggle on every page; 山水-style interface.
