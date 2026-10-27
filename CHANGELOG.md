# Changelog · 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Changed · 改进
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
