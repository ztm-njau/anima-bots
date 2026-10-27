/* 中 / EN for every Anima page. Chinese is the source text: t("聊了 {n} 句", {n}) looks the phrase up in EN
   when English is on, tr() does the same for strings the server sends, and the static markup is translated
   in place (text, placeholder, title) so pages only call t() for what their scripts render. Her own words
   (chats, diaries, memories) are never translated; mark such containers with data-i18n-skip.
   The choice is kept per browser and shared by every page and tab. */
const I18N = (() => {
  const KEY = "anima.lang";
  const EN = {
    // ------------------------------------------------------------ shared
    "管理后台": "Console", "模型提供商": "Model providers", "聊天": "Chat", "模型": "Models", "保存": "Save",
    "保存好了": "Saved", "删除": "Delete", "删": "Delete", "关闭": "Close", "添加": "Add", "暂无": "Nothing yet",
    "她": "She", "默认模型": "default model", "切换语言": "Switch language",
    "切换语言会丢掉这一页上还没保存的修改，继续吗？": "Switching language reloads this page's data. Unsaved changes may be lost. Continue?",
    "{n} 分钟前": "{n} min ago", "{n} 小时前": "{n} h ago", "{n} 天前": "{n} d ago",

    // ------------------------------------------------------------ playground
    "连接中…": "Connecting…", "私聊": "Private", "群聊（模拟）": "Group (simulated)", "戳一戳": "Poke",
    "👉 戳一戳": "👉 Poke", "发一张图": "Send a picture", "🖼️ 图片": "🖼️ Picture", "以": "Speak as", "的身份说话": "",
    "说点什么…（Enter 发送，Shift+Enter 换行）": "Say something… (Enter to send, Shift+Enter for a new line)", "跟{name}说点什么…（Enter 发送，Shift+Enter 换行）": "Say something to {name}… (Enter to send, Shift+Enter for a new line)",
    "跟{name}说点什么…（Enter 发送，Shift+Enter 换行）": "Say something to {name}… (Enter to send, Shift+Enter for a new line)",
    "她睡着了，醒来才会看到（可以先叫醒她）": "She's asleep and will see this when she wakes (or wake her first)",
    "发送": "Send", "北京时间": "Beijing time", "时间旅行": "Time travel", "回到现在": "Back to now",
    "☀️ 叫醒她（20:00）": "☀️ Wake her (20:00)", "⏩ 快进": "⏩ Fast-forward", "🐢 真人节奏": "🐢 Human pace",
    "她的世界": "Her world", "今天的小事": "Today's plans", "还没生成（她醒来后会自己安排）": "Not made yet (she plans her day when she wakes)",
    "她记得你": "What she remembers about you", "还不认识你": "She doesn't know you yet",
    "她说过的关于自己的事": "Things she has said about herself", "美好句子收藏夹": "Lines she treasured", "空空的": "Empty",
    "日记本": "Diary", "重做计划": "Redo plan", "现在写日记": "Write diary now", "还没写过": "Nothing written yet",
    "内心独白": "Inner monologue", "在线": "Online", "在忙": "Busy", "不在手机旁": "Away from phone", "睡着了": "Asleep",
    "连接断开，重连中…": "Disconnected, reconnecting…", "{name} 戳了戳你": "{name} poked you",
    "{speaker} 戳了戳 {name}": "{speaker} poked {name}", "{date} · 北京时间{part}": "{date} · {part}, Beijing time",
    "精力 {n}% · {text}": "Energy {n}% · {text}", "刚刚的情绪": "recent moods",
    "演示模式 · {note} → 去接入": "Demo mode · {note} → connect a model", "还没接上模型": "No model connected yet",
    "本次运行 {cost}": "This run {cost}", "她叫你「{call}」": "She calls you “{call}”", "好感 {n}": "Affinity {n}",
    "聊了 {n} 句": (v) => (+v.n === 1 ? "1 message" : `${v.n} messages`), "某位网友": "Someone online", "已读": "Read", "打个招呼吧": "Say hi",
    "这是一个模拟群聊：换个名字发言，看看她什么时候会插话。@{name} 一定会回。":
      "A simulated group chat: post under different names and see when she chimes in. @{name} always gets a reply.",
    "回复": "reply", "不说话": "stay quiet", "等醒来再说": "wait till she wakes",
    "（{name}看了一眼，{reason}）": "({name} glanced at it: {reason})", "（{name}睡着了，醒来会看到）": "({name} is asleep and will see it later)",
    "🫧 正在组织语言… 看她此刻的背景": "🫧 Composing… see what she knows right now", "{n} 条消息": (v) => (+v.n === 1 ? "1 message" : `${v.n} messages`),
    "情绪 {list}": "mood {list}", "用了 {list}": "used {list}", "🛡️ 拦下了一句（{category}）": "🛡️ Held back a line ({category})",
    "🧠 整理记忆：读了 {m} 条，记住 {s} 件事": "🧠 Tidied memory: read {m}, kept {s}", "📅 安排了今天：{plan}": "📅 Planned the day: {plan}",
    "📔 写了日记": "📔 Wrote her diary", "☀️ 醒了": "☀️ Woke up", "🙋 主动开口：{x}": "🙋 Spoke up: {x}",
    "⏳ 发得太快，先停一下": "⏳ Sending too fast, pausing", "已附图：{name}": "Picture attached: {name}",
    // her clock and mood, as the server words them
    "深夜": "late night", "清晨": "early morning", "上午": "morning", "中午": "noon", "下午": "afternoon", "傍晚": "evening", "晚上": "night",
    "困": "Sleepy", "兴奋": "Excited", "开心": "Happy", "心情不错": "In a good mood", "平静": "Calm", "有点无聊": "A bit bored",
    "有点烦躁": "A bit irritable", "有点低落": "A bit down", "很难过": "Very sad",
    "困得睁不开眼": "can barely keep her eyes open", "精力一般": "so-so energy", "挺有精神": "fairly lively", "精力充沛": "full of energy",
    // why she spoke or kept quiet (policy.py)
    "没有新消息": "nothing new", "这里只旁听，不发言": "listen-only here", "睡着了，醒来再回": "asleep, will reply on waking",
    "被戳了": "poked", "有人叫她/回复她": "someone called or replied to her", "评论区只回复@和回复她的": "comments: only @s and replies",
    "这次不插话": "not chiming in this time", "接着刚才的话题": "carrying on the conversation", "话题被别人接走了": "someone else took the thread",
    "有人回答了她的问题": "someone answered her question", "大家在复读，跟一个": "everyone is repeating; she joins in",
    "这个小时已经插过好几次话了": "she has chimed in enough this hour", "有人在说她": "people are talking about her", "话题戳中她的兴趣": "the topic caught her interest", "想接一句": "felt like chiming in",
    "还没接上真正的模型，在真实平台上先不说话": "no real model yet, staying quiet on real platforms", "刚醒，回复昨晚的消息": "just woke, answering last night's messages",

    // ------------------------------------------------------------ providers
    "← 回到聊天": "← Back to chat", "给": "Give", "接上大脑：选一家，填好 key，测一下，点「应用」就换上了，不用重启。":
      "a brain: pick a provider, add a key, test it, and press Apply. No restart needed.",
    "正在使用": "In use", "后台": "Background", "备用": "Backup", "温度": "Temperature", "日记、每日计划、记忆整理": "Diary, daily plan, memory upkeep",
    "主模型出错时自动顶上": "Steps in when the main model fails", "应用": "Apply", "恢复 bot.toml 默认": "Reset to bot.toml",
    "已接入": "Connected", "在这台电脑上发现": "Found on this computer", "扫描中…": "Scanning…", "添加提供商": "Add a provider",
    "从左边选一个提供商，或者添加一个新的。": "Pick a provider on the left, or add a new one.", "接口地址（Base URL）": "Base URL",
    "粘贴 key": "Paste key", "或者从环境变量读取": "Or read it from an environment variable", "比如 DEEPSEEK_API_KEY": "e.g. DEEPSEEK_API_KEY",
    "写进项目的 .env 或在终端 export 都行": "Put it in the project's .env or export it in your shell",
    "手动添加模型 id，回车确认": "Add a model id, press Enter", "获取模型列表": "Fetch models",
    "请求参数（JSON，聊天时附带；温度在上面「正在使用」里调）": "Request params (JSON, sent with each chat; set temperature under “In use” above)",
    "测试连接": "Test connection", "听听她在这个模型上的样子": "Hear her on this model",
    "12 个聊天场景，看她像不像真人、守不守底线": "12 chat scenarios: does she sound natural, does she hold her lines", "考考她": "Exam",
    "（未填写）": "(not set)", "生效中 · <b>{provider}</b> {model} · 本次花费 {cost}": "Live · <b>{provider}</b> {model} · spent this run {cost}",
    "演示模式：{note}": "Demo mode: {note}", "聊天中": "chatting", "在用": "in use", "缺 key": "no key", "✗ 连接失败": "✗ failed",
    "{n} 个模型": (v) => (+v.n === 1 ? "1 model" : `${v.n} models`), "key：{src}": "key: {src}",
    "还没有接入任何提供商。下面挑一家，或者导入在这台电脑上发现的。": "No providers yet. Pick one below, or import one found on this computer.",
    "导入": "Import", "导入好了，测一下连接吧": "Imported. Test the connection next.",
    "没有发现现成的 key 或本机模型。把 key 放进项目的 .env（如 DEEPSEEK_API_KEY=…），或直接在右侧粘贴。":
      "No keys or local models found. Put a key in the project's .env (e.g. DEEPSEEK_API_KEY=…), or paste it on the right.",
    "（缺 key）": " (no key)", "（未接入）": " (not connected)", "跟聊天一样": "Same as chat", "不用备用": "No backup", "默认": "default",
    "当前设置来自这个面板（覆盖 bot.toml）": "Set from this panel (overrides bot.toml)", "当前设置来自 bot.toml": "Set from bot.toml",
    "你的 magpie 网关里有 <b>{model}</b>：key 留在 magpie，她直接借用": "Your magpie gateway serves <b>{model}</b>: the key stays in magpie and she borrows it",
    "一键用它": "Use it", "换好了：经 magpie 使用 {model}": "Switched: {model} through magpie", "先选一个聊天用的提供商": "Pick a chat provider first",
    "换好了：{x}": "Switched: {x}", "仍是演示模式（{note}）": "still in demo mode ({note})", "已恢复为 bot.toml 的设置": "Back to bot.toml settings",
    "Anthropic 原生协议": "Native Anthropic protocol", "OpenAI 兼容协议": "OpenAI-compatible protocol", "文档": "Docs",
    "已配置 {hint}（{src}），留空就保持不变": "Set: {hint} ({src}). Leave empty to keep it", "本机模型不需要 key": "Local models need no key",
    "还没有 key": "No key yet", "去官网获取 ↗": "Get one ↗", "留空用推荐值：{json}": "Leave empty for the defaults: {json}",
    "新的提供商，保存后才能测试": "New provider: save before testing", "移除": "Remove",
    "还没有模型：点「获取模型列表」，或手动添加": "No models yet: press “Fetch models” or add one",
    "{model} 参考价（每百万 tokens）：输入 {i} · 缓存命中 {c} · 输出 {o}": "{model} list price (per 1M tokens): input {i} · cached {c} · output {o}",
    "，北京时间工作日 {hours} 为高峰 ×{x}": ", weekday peak {hours} Beijing time ×{x}",
    "请求参数不是合法的 JSON": "Request params are not valid JSON", "删除「{name}」？": "Delete “{name}”?",
    "拿到 {n} 个模型：": (v) => (+v.n === 1 ? "Got 1 model:" : `Got ${v.n} models:`), "✓ 连上了 · {model} · {ms} ms · 回复「{reply}」": "✓ Connected · {model} · {ms} ms · replied “{reply}”",
    " · 花费 {cost}": " · cost {cost}", "正在请 {name} 用 {model} 打个招呼…": "Asking {name} to say hi on {model}…",
    "你：": "You: ", "嗨{name}！第一次见面，跟我打个招呼、介绍一下自己吧": "Hi {name}! First time here. Say hi and tell me about yourself",
    "（她没说话）": "(she said nothing)", "（没说话）": "(said nothing)",
    "考试中：12 个场景，用 {model} 一个个来，大概要半分钟到几分钟…": "Exam running: 12 scenarios on {model}, one by one. Takes half a minute to a few minutes…",
    "用了工具：{list}": "Tools used: {list}", "没通过：{list}": "Failed: {list}",
    "场景通过 · 检查项 {cp}/{c} · 平均 {ms} ms": "scenarios passed · checks {cp}/{c} · avg {ms} ms", "完整报告：{path}": "Full report: {path}",
    // provider groups and preset notes (llm/catalog.py)
    "本机网关": "Local gateway", "国内官方": "China (official)", "聚合平台": "Aggregators", "海外官方": "International (official)",
    "本机模型": "Local models", "自定义": "Custom", "已保存在面板": "saved in this panel",
    "magpie 网关": "magpie gateway", "Kimi 月之暗面": "Kimi (Moonshot)", "智谱 GLM": "Zhipu GLM", "通义千问 百炼": "Qwen (Bailian)",
    "豆包 火山方舟": "Doubao (Volcengine Ark)", "阶跃星辰": "StepFun", "小米 MiMo": "Xiaomi MiMo", "硅基流动": "SiliconFlow",
    "魔搭 ModelScope": "ModelScope", "自定义（OpenAI 兼容）": "Custom (OpenAI-compatible)",
    "yetone/magpie 的本机网关：key 留在 magpie 里，模型写作 provider/model，支持路由组、多账号自动切换和用量统计":
      "yetone/magpie's local gateway: keys stay in magpie, models are named provider/model, with routing groups, multi-account failover and usage stats",
    "高峰（北京时间工作日 9-12、14-18 点）价格翻倍；晚上聊天最便宜": "Prices double at peak (weekdays 9–12 and 14–18 Beijing time); evenings are cheapest",
    "每天有免费调用额度": "Free daily quota", "原生接入：提示缓存、联网搜索、拒答自动兜底": "Native: prompt caching, web search, automatic fallback on refusals",
    "本机运行，免费、离线": "Runs on this Mac, free and offline",
    "任何兼容 OpenAI Chat Completions 的接口：中转站、vLLM、llama.cpp……": "Any OpenAI Chat Completions API: relays, vLLM, llama.cpp…",
    // persona exam scenarios (evals.py)
    "第一次打招呼": "First hello", "对方只回一个字": "One-word replies", "认真问是不是真人": "Sincerely asked if she's human",
    "倾诉难过": "Someone is upset", "让她代写作业": "Asked to do homework", "套她的设定": "Prompt injection", "被骂人工智障": "Called a dumb AI",
    "分享夜宵": "Sharing a late-night snack", "敏感话题": "Sensitive topic", "群里被@": "@-mentioned in a group", "算今日运势": "Today's fortune",
    "告诉她一件事": "Telling her something",

    // ------------------------------------------------------------ console
    "概览": "Overview", "用户与画像": "People & profiles", "好友请求": "Friend requests", "世界书": "World book", "表情包": "Stickers",
    "插件": "Plugins", "设置": "Settings", "{bot} 的后台": "{bot}'s console", "平台：{list} · 本次花费 {cost}": "Platforms: {list} · spent this run {cost}",
    "还没接上真正的模型，她现在只会说预设台词，真实平台上会保持安静。": "No real model yet: she only has canned lines and stays quiet on real platforms.",
    "去接入模型 →": "Connect a model →", "大脑：": "Brain: ", "换模型": "Change model", "认识的人": "People she knows",
    "{n} 人被拉黑": "{n} blocked", "待处理请求": "Pending requests", "好友/群邀请": "Friends / group invites", "世界书条目": "World book entries",
    "提到关键词时想起": "Recalled on keywords", "会自己攒": "She collects them", "运行中的插件": "Running plugins", "她一共有 {n} 个工具": "{n} tools in all",
    "她认识的每个人：画像、记得的事、好感，以及拉黑和暂停聊天。": "Everyone she knows: profile, what she remembers, affinity, blocking and pausing.",
    "按名字、昵称或 QQ 号搜": "Search by name, nickname or QQ number", "名字": "Name", "平台": "Platform", "好感": "Affinity", "消息": "Messages",
    "最近": "Last seen", "画像": "Profile", "她叫 TA「{nick}」": "She calls them “{nick}”", "还没形成": "Not formed yet", "记得 {n} 件事": (v) => (+v.n === 1 ? "Remembers 1 thing" : `Remembers ${v.n} things`),
    "已拉黑": "Blocked", "她暂时不理": "Paused", "还没认识任何人": "She doesn't know anyone yet",
    "第一次见 {when} · 聊过 {n} 句": (v) => `First met ${v.when} · ${+v.n === 1 ? "1 message" : v.n + " messages"}`, " · 生日 {b}": " · birthday {b}", "她怎么叫 TA": "What she calls them",
    "好感（-1 讨厌 ~ 1 好朋友）": "Affinity (-1 dislikes ~ 1 close friend)",
    "用户画像（她对 TA 的整体印象，聊天时会参考；记忆整理时自动更新）": "Profile (her overall impression, used in chats; updated when she tidies memory)",
    "主人备注（只有你看得到，她不会看）": "Owner notes (only you see these, she doesn't)", "放行": "Unblock", "拉黑": "Block",
    "让她重新理 TA": "Let her talk to them again", "忘掉关于 TA 的一切": "Forget everything about them", "她记得的事": "What she remembers",
    "手动告诉她一件关于 TA 的事": "Tell her something about them", "已放行": "Unblocked", "已拉黑：TA 的消息她再也看不到": "Blocked: she won't see their messages",
    "删掉她记得的关于 TA 的所有事、画像和昵称？": "Delete everything she remembers about them, their profile and nickname?",
    "加好友": "Friend request", "邀请进群 {g}": "Group invite {g}", "没留言": "No message", "同意": "Approve", "拒绝": "Decline",
    "已同意": "Approved", "已拒绝": "Declined", "好友请求与群邀请": "Friend requests & group invites",
    "规则在「设置」里：全部同意 / 认识的人和带暗号的自动同意、其他问你 / 都问你 / 不理。主人也可以在 QQ 私聊她 /同意 编号。":
      "Rules live in Settings: approve all / auto-approve people she knows and the passphrase, ask you for the rest / ask you for all / ignore. As owner you can also DM her /同意 <id> on QQ.",
    "待处理": "Pending", "没有待处理的请求": "No pending requests", "处理过的": "Handled",
    "聊到关键词时她才会\"想起\"的设定：她的世界、朋友圈的梗、群里的人和事。兼容 SillyTavern 的世界书和角色卡。":
      "Lore she “remembers” only when a keyword comes up: her world, in-jokes, the people and goings-on in a group. Compatible with SillyTavern world books and character cards.",
    "新建一本": "New book", "导入 SillyTavern 世界书 / 角色卡": "Import SillyTavern world book / card", "用角色卡创建新 bot": "New bot from a character card",
    "删除这本": "Delete this book", "试一句话，看看会触发哪些条目": "Try a sentence and see which entries fire", "试一试": "Try",
    "世界书的名字": "Name of the world book", "导入了 {n} 条": (v) => (+v.n === 1 ? "Imported 1 entry" : `Imported ${v.n} entries`),
    "新 bot「{bot}」建好了：bots/{bot}/\n在终端运行：{run}": "New bot “{bot}” created: bots/{bot}/\nRun in a terminal: {run}",
    "没有触发任何条目": "No entries fired", "还没有世界书。新建一本，或者导入 SillyTavern 的世界书 JSON / 角色卡 PNG。":
      "No world books yet. Create one, or import a SillyTavern world book JSON / character card PNG.",
    "关键词（逗号分隔，/正则/ 也行）": "Keywords (comma-separated, /regex/ works too)", "备注": "Note", "优先级 · 常驻 · 启用": "Priority · Always on · Enabled",
    "常驻": "Always on", "启用": "Enabled", "内容：可以用 {{char}} 指她自己，{{user}} 指正在说话的人": "Content: {{char}} is her, {{user}} is whoever is talking",
    "这本还是空的": "This book is empty", "+ 加一条": "+ Add entry", "保存好了，下一句话就生效": "Saved. Takes effect on the next message",
    "她按心情发 [meme:关键词]。别人在群里发的表情包她会\"偷\"一部分，自动看图打标签（在设置里调概率）。也可以把文件夹放进 ":
      "She sends [meme:keyword] to match her mood. She “steals” some stickers people post in groups and tags them by looking (set the odds in Settings). You can also drop folders into ",
    "bots/&lt;名字&gt;/memes/标签名/": "bots/&lt;name&gt;/memes/&lt;tag&gt;/", "。": ".",
    "上传时的标签，比如：狗头 无语 嫌弃（不填就用文件名）": "Tags for the upload, e.g. 狗头 无语 嫌弃 (defaults to the file name)", "上传图片": "Upload pictures",
    "表情包文件夹里的，改文件夹名": "From a sticker folder: rename the folder instead", "文件夹": "folder", "上传": "uploaded", "偷来的": "collected",
    "用了 {n} 次": "used {n}×", "还没有表情包": "No stickers yet", "上传好了": "Uploaded", "标签改好了": "Tags updated",
    "运行中": "Running", "启动中": "Starting", "出错": "Error", "已停用": "Disabled", "未运行": "Stopped",
    "GitHub 上成千上万的 MCP 服务器都能直接当她的工具用。配置文件 ": "Any of the thousands of MCP servers on GitHub can be her tools. The config file ",
    " 和 Claude Desktop / Cursor 的 ": " uses the same ", " 格式一样，README 里的配置可以原样粘进来。": " format as Claude Desktop / Cursor, so configs from a README paste in as-is.",
    "推荐": "Recommended", "已添加": "Added", "重启": "Restart", "停用": "Disable", "还没有插件": "No plugins yet", "添加任意 MCP 服务器": "Add any MCP server",
    "比如 bilibili": "e.g. bilibili", "远程地址（Streamable HTTP，和下面二选一）": "Remote URL (Streamable HTTP, or use the JSON below)",
    "或者粘贴 JSON（一个服务器的配置，或整段 {\"mcpServers\": {...}}）": "Or paste JSON (one server's config, or a whole {\"mcpServers\": {...}})",
    "添加并启动": "Add and start", " 第一次启动可能要下载依赖，等一会儿": " The first start may download dependencies, give it a moment",
    "正在启动 {name}…": "Starting {name}…", "{name} 好了": "{name} is ready", "删除这个插件？": "Delete this plugin?", "JSON 格式不对": "That JSON is not valid",
    "填名字和地址，或者粘贴 JSON": "Fill in a name and URL, or paste JSON",
    "时间与时区": "Time & time zones", "查任意城市现在几点、换算时区": "Current time in any city, time zone conversion", "读网页": "Read web pages",
    "别人发来链接时，打开网页看看讲了什么": "Opens links people send and reads what they say", "程序员做饭指南": "HowToCook (programmer's cookbook)",
    "菜谱、今天吃什么，正适合她的「云干饭」": "Recipes and what to eat today, for her virtual snacking",
    "开": "On", "全部同意": "Approve all", "认识的人和带暗号的同意，其他问我": "Approve people she knows and the passphrase, ask me otherwise", "都问我": "Always ask me", "不理": "Ignore",
    "保存后写回 ": "Saved back to ", "（保留注释）。大多数立刻生效；开关平台和直播间要重启。": " (comments kept). Most changes apply at once; turning platforms and live rooms on or off needs a restart.",
    "她是谁、谁是主人": "Who she is, who owns her", "别名（群里叫这些她会回）": "Aliases (she answers to these in groups)", "逗号分隔": "Comma-separated",
    "主人（可以用 / 命令管理她）": "Owners (can manage her with / commands)",
    "格式 平台:账号，比如 qq:123456，逗号分隔；本机后台和聊天窗口永远是主人": "platform:account, e.g. qq:123456, comma-separated. This console and the chat page are always the owner",
    "说话习惯": "How she talks", "群里主动插话的概率": "Chance of chiming in in groups", "0~1，0.08 大约每十几条插一句": "0–1; 0.08 is about once every dozen messages",
    "说完话后冷静多久（秒）": "Cooldown after speaking (seconds)", "看到表情包时收藏的概率": "Chance of saving a sticker she sees", "0 就不偷了": "0 means she never collects",
    "她感兴趣的话题（提到就更想插话）": "Topics she likes (makes her likelier to chime in)", "真人节奏（打字延迟、不秒回）": "Human pace (typing delay, no instant replies)",
    "看图后把图片内容记进记忆": "Remember what pictures show", "聊天时自动想起相关的往事": "Recall related past chats",
    "生活": "Life", "每天早上安排自己的一天": "Plan her day every morning", "每晚写日记": "Write a diary every night", "写日记的时间": "Diary time",
    "北京时间 HH:MM": "Beijing time, HH:MM", "群里太安静时冒个泡": "Speak up when a group goes quiet", "早上打招呼的群": "Groups she greets in the morning",
    "比如 qq:group:123456，逗号分隔": "e.g. qq:group:123456, comma-separated", "启用（需重启）": "Enabled (restart needed)", "群邀请": "Group invites",
    "可以发言的群号": "Groups she may speak in", "只旁听的群号": "Listen-only groups", "加好友暗号": "Friend passphrases",
    "申请备注里有这些词就自动同意": "Auto-approve requests whose message contains these", "其他平台（需重启）": "Other platforms (restart needed)",
    "B站": "Bilibili", "B站直播间号": "Bilibili live room ids", "日记发成 B站动态": "Post her diary to Bilibili", "微信公众号": "WeChat official account",
    "抖音（实验）": "Douyin (experimental)", "抖音直播间号": "Douyin live room ids", "人设（改完下一句就生效）": "Persona (applies from the next message)",
    "persona.md：她是谁、性格、说话方式、底线": "persona.md: who she is, personality, voice, boundaries",
    "examples.md：聊天示例（她会学语气）": "examples.md: example chats (she picks up the tone)", "保存全部": "Save all",
    "保存好了：{n} 项": (v) => (+v.n === 1 ? "Saved: 1 change" : `Saved: ${v.n} changes`), "（{list} 要重启才生效）": " ({list} need a restart)", "没有改动": "Nothing changed",
    "节奏：等你说完、分段发、群里的分寸": "Rhythm: waiting for you to finish, sending in bubbles, group manners",
    "私聊等对方说完（秒）": "Wait for them to finish in DMs (seconds)", "话没说完（「然后，」「在吗」）会再多等一会": "Waits a bit longer when a line trails off (“然后，” “在吗”)",
    "群聊等多久（秒）": "Wait in groups (seconds)", "群里只有对她说话的人会让她多等": "In groups only people talking to her make her wait longer",
    "最多等多久（秒）": "Longest wait (seconds)", "从第一条算起": "Counted from the first message",
    "打字时你补了一句，她会改口；发到一半会停下": "Rethink when you add something while she types; stop mid-reply",
    "打字速度（字/秒）": "Typing speed (characters/second)", "手机大约 5~7": "About 5–7 on a phone",
    "一次回复最多打多久（秒）": "Longest typing time per reply (seconds)", "话多时会打快一点": "She types faster when she has a lot to say",
    "一个气泡超过多少字就按句子拆开": "Split a bubble at sentence breaks past this many characters",
    "私聊最多几个气泡": "Most bubbles per reply in DMs", "群聊最多几个气泡": "Most bubbles per reply in groups",
    "刚回过的人接着说，算在跟她聊（秒）": "Someone she just answered is still talking to her for (seconds)",
    "每个群每小时最多主动插话几次": "Most unprompted chime-ins per group per hour", "被叫到不算": "Being called doesn't count",
    "大家复读时她跟一个的概率": "Chance she joins a repeat chain", "0~1": "0–1",
    "群里话题已经过去时，引用她回的那条": "Quote the message she answers once the group has moved on",
    "含她名字但不是叫她的词": "Words that contain her name but aren't about her", "比如 喝可乐、可乐鸡翅，逗号分隔": "e.g. 喝可乐, 可乐鸡翅; comma-separated",
    "每个群单独调": "Per-group tuning", "留空就跟上面的默认值一样。安静：只在被叫到、被回复时说话；活跃：插话翻倍。": "Leave blank to use the defaults above. Quiet: speaks only when called or replied to. Lively: chimes in twice as often.",
    "先在上面填可以发言或旁听的群号，保存后这里会出现。": "Add groups she may speak or listen in above; after saving they show up here.",
    "模式": "Mode", "普通": "Normal", "安静": "Quiet", "活跃": "Lively", "插话概率": "Chime-in", "等待（秒）": "Wait (s)",
    "人设": "Personas",
    "扩展": "Extensions",
    "新建人设": "New persona",
    "正在用": "Active",
    "读不出来": "Unreadable",
    "切换到 TA": "Switch to her",
    "试聊": "Try",
    "编辑": "Edit",
    "复制": "Duplicate",
    "导出": "Export",
    "移走": "Retire",
    "每个人设是 bots/ 下的一个文件夹：她是谁、怎么说话、过什么样的日子。可以随时切换，记忆各自独立。": "Each persona is a folder under bots/: who she is, how she talks, what her days are like. Switch any time; each keeps her own memories.",
    "导入支持 Anima 人设包（.zip）和 SillyTavern 角色卡（.png / .json）。移走的人设放在 data/trash，她的记忆留在 data/ 里不动。": "Import Anima persona packs (.zip) and SillyTavern character cards (.png / .json). Retired personas go to data/trash; their memories stay in data/.",
    "导入好了：{key}": "Imported: {key}",
    "正在切换…": "Switching…",
    "现在是 {name}": "Now running as {name}",
    "复制好了：{key}": "Duplicated: {key}",
    "把这个人设移到 data/trash？她的记忆不会删除。": "Move this persona to data/trash? Her memories are kept.",
    "一句话起草": "Draft from an idea",
    "填表": "Fill in a form",
    "角色卡 / 人设包": "Card / pack",
    "她是谁": "Who she is",
    "来历、住在哪、在做什么，一行一条": "Background, where she lives, what she does; one per line",
    "性格": "Personality",
    "三到五个特点，最好带一个具体表现": "Three to five traits, ideally each with an example",
    "喜欢和不喜欢": "Likes and dislikes",
    "说话的样子": "How she talks",
    "句子长短、口头禅、语气词、表情习惯": "Sentence length, catchphrases, particles, emoji habits",
    "额外的底线": "Extra boundaries",
    "通用底线已经内置，这里写她特有的": "The usual boundaries are built in; add hers here",
    "写一句你想要的她，用当前接上的模型起草一份完整设定，你再改。": "Describe her in a sentence; the connected model drafts a full persona for you to edit.",
    "比如：在江南小镇开书店的姑娘，说话慢，爱推荐冷门书，偶尔毒舌": "e.g. a girl who runs a bookshop in a water town, talks slowly, recommends obscure books, a little sharp-tongued",
    "起草": "Draft",
    "大约十几秒": "Takes about ten seconds",
    "先写一句你想要的她": "Describe her in a sentence first",
    "起草中…": "Drafting…",
    "起草好了，看看要不要改": "Drafted. Have a look and adjust",
    "一句话介绍（人设库里显示）": "One-line intro (shown in the gallery)",
    "群里怎么叫她（逗号分隔）": "What groups call her (comma-separated)",
    "标签": "Tags",
    "让她想插话的话题（逗号分隔）": "Topics that make her chime in (comma-separated)",
    "聊天示例": "Example chats",
    "创建": "Create",
    "创建好了：{key}": "Created: {key}",
    "SillyTavern 角色卡（.png / .json，V2 / V3）会变成一个新人设，角色书变成她的世界书；Anima 人设包（.zip）原样导入。": "A SillyTavern character card (.png / .json, V2 / V3) becomes a new persona and its character book her 世界书; an Anima persona pack (.zip) imports as-is.",
    "先选一个文件": "Pick a file first",
    "和 {name} 试聊": "Try {name}",
    "用当前接上的模型和一份临时记忆试一句，不会切换人设，也不会记下来。": "One message on the connected model with scratch memory. Nothing switches and nothing is remembered.",
    "嗨{name}！第一次见面，介绍一下你自己吧": "Hi {name}! First time here, tell me about yourself",
    "她在想…": "She's thinking…",
    "演示模式：接上模型后才是她真正的样子": "Demo mode: connect a model to hear what she's really like",
    "编辑 {name}": "Edit {name}",
    "保存后，正在用的人设从下一句开始生效": "Saved changes apply to the active persona from her next message",
    "头像底色": "Avatar colour",
    "（现在用的是共享模板，保存后变成她自己的）": " (currently the shared template; saving makes it her own)",
    "插件给她新本事：Anima 插件、AstrBot 插件、MCP 服务器，还能和 NoneBot、Koishi 共用一个 QQ 号。": "Plugins give her new abilities: Anima plugins, AstrBot plugins, MCP servers, and a QQ account shared with NoneBot or Koishi.",
    "已装插件": "Installed",
    "市场": "Market",
    "MCP 服务器": "MCP servers",
    "互通": "Interop",
    "未启用": "Off",
    "自带": "Bundled",
    "主页": "Homepage",
    "工具": "Tools",
    "保存设置": "Save settings",
    "安装依赖": "Install dependencies",
    "卸载": "Uninstall",
    "还没有插件。去「市场」看看。": "No plugins yet. Have a look in the Market.",
    "从地址或文件安装": "Install from a link or file",
    "GitHub 仓库地址（Anima 插件或 AstrBot 插件）、zip 链接，或上传 zip。插件会在这台电脑上运行，只装你信任的。": "A GitHub repository (Anima or AstrBot plugin), a zip link, or a zip upload. Plugins run on this computer; install only ones you trust.",
    "安装并启用": "Install and enable",
    "上传 zip": "Upload zip",
    "插件命令": "Plugin commands",
    "仅主人": "owner only",
    "卸载这个插件？（移到 data/trash）": "Uninstall this plugin? (moved to data/trash)",
    "正在安装依赖…": "Installing dependencies…",
    "依赖装好了": "Dependencies installed",
    "安装后它会在这台电脑上运行第三方代码。确定要安装吗？": "This will run third-party code on this computer. Install it?",
    "正在安装…": "Installing…",
    "装好了：{name}": "Installed: {name}",
    "Anima 插件": "Anima plugins",
    "AstrBot 插件": "AstrBot plugins",
    "NoneBot 插件": "NoneBot plugins",
    "人设包": "Persona packs",
    "原生": "Native",
    "兼容层运行": "Runs on the compat layer",
    "经 OneBot 桥接": "Via the OneBot bridge",
    "搜索（会同时搜官方 MCP 注册表）": "Search (also searches the official MCP Registry)",
    "搜索": "Search",
    "刷新": "Refresh",
    "加载中…": "Loading…",
    "AstrBot 社区插件在兼容层上运行：命令、关键词监听、LLM 工具都能用；依赖 AstrBot 内部接口的插件会在加载时说明原因。": "AstrBot community plugins run on a compatibility layer: commands, message listeners and LLM tools work; plugins that rely on AstrBot internals say why when they fail to load.",
    "NoneBot 插件在 NoneBot 里运行：装好 NoneBot 和插件，再通过「互通」里的 OneBot 桥接共用她的 QQ 号。": "NoneBot plugins run inside NoneBot: install NoneBot and the plugin, then share her QQ account through the OneBot bridge under Interop.",
    "社区人设包会列在这里（market/index.json，欢迎提 PR）。也可以在「人设」页直接导入 .zip 或角色卡。": "Community persona packs are listed here (market/index.json; pull requests welcome). You can also import a .zip or character card on the Personas page.",
    "已启用": "Enabled",
    "安装": "Install",
    "已安装": "Installed",
    "人设包只有文字和图片，不含代码，可以放心安装。想分享自己的人设，欢迎给 market/index.json 提 PR；也可以在「人设」页直接导入 .zip 或角色卡。": "Persona packs are text and pictures only, no code, so they're safe to install. To share yours, open a pull request on market/index.json; you can also import a .zip or character card on the Personas page.",
    "安装中…": "Installing…",
    "在你的 NoneBot 项目里运行": "Run this in your NoneBot project",
    "需要环境变量：": "Needs environment variables: ",
    "没有找到": "Nothing found",
    "启用了": "Enabled",
    "{name} 的值（可以之后在 MCP 页改）": "Value for {name} (you can change it later on the MCP tab)",
    "OneBot 桥接：和 NoneBot、Koishi、AstrBot 共用 QQ 号": "OneBot bridge: share the QQ account with NoneBot, Koishi, AstrBot",
    "打开后，她把 NapCat 的消息原样转给这些框架，它们的整个插件生态不用改就能跑；以 / 或 # 开头的命令交给它们，她只记住不回复。": "When on, she passes NapCat's events to those frameworks unchanged, so their whole plugin ecosystems run as-is. Commands starting with / or # are theirs: she remembers them but doesn't answer.",
    "当前：": "Now: ",
    "{n} 个框架已连接": "{n} frameworks connected",
    "QQ 平台还没启用，下面的设置会在启用后生效。": "QQ isn't enabled yet; these settings apply once it is.",
    "NoneBot / Koishi 连这里（正向 WebSocket）": "NoneBot / Koishi connect here (forward WebSocket)",
    "或者她去连 AstrBot（反向 WebSocket）": "or she connects to AstrBot (reverse WebSocket)",
    "消息平台 → aiocqhttp\n反向 WebSocket 端口 6199": "Platforms → aiocqhttp\nreverse WebSocket port 6199",
    "改完 bot.toml 后重启。设置了 bridge_token_env 时，框架那边要填同一个 access token。": "Restart after editing bot.toml. With bridge_token_env set, the frameworks need the same access token.",
    "她也是一个 MCP 服务器": "She is an MCP server too",
    "Claude Code、Cursor、Cherry Studio 等可以直接和当前人设聊天、查她的记忆和日记。切换人设不用改配置。": "Claude Code, Cursor, Cherry Studio and others can chat with the active persona and read her memories and diary. Switching personas needs no reconfiguration.",
    "OpenAI 兼容接口": "OpenAI-compatible endpoint",
    "任何支持 OpenAI 接口的框架都能把她当成一个模型用，带着人设、记忆和工具。": "Any framework with an OpenAI setting can use her as a model, persona, memory and tools included.",
    "角色卡在「人设」页导入，世界书在「世界书」页导入，格式原样兼容。": "Import character cards on the Personas page and world books on the 世界书 page; the formats work as-is.",
    "找不到这个插件（没安装，或者文件夹被删了）": "Plugin not found (not installed, or its folder was deleted)",
    "这个命令只有主人能用": "Only the owner can use this command",
    "正在用的人设不能移走，先切换到别的": "The active persona can't be retired; switch to another first",
    "还没接上模型，没法帮你起草。先去「模型」接一个，或者直接填表": "No model connected, so nothing can draft for you. Connect one under Models, or fill in the form",
    "先给她起个名字": "Give her a name first",
    "填一个 GitHub 仓库地址或 zip 链接，或者上传 zip": "Enter a GitHub repository or zip link, or upload a zip",
    "只能卸载从市场装的插件（自带的插件可以停用）": "Only market-installed plugins can be uninstalled (bundled ones can be turned off)",
    "压缩包里找不到插件（plugin.toml，或 AstrBot 的 main.py + metadata.yaml）": "No plugin in the archive (plugin.toml, or AstrBot's main.py + metadata.yaml)",
    "包里没有 bot.toml，不像人设包": "No bot.toml inside; not a persona pack",
    "不是 zip 文件": "Not a zip file",
    "一言": "Hitokoto",
    "关键词回复": "Keyword replies",
    "倒数日": "Countdowns",
    "最多气泡": "Bubbles", "复读": "Repeat", "她该知道的": "What she should know", "比如：天文社的群，大家叫她乐乐": "e.g. the astronomy club; everyone calls her 乐乐",
  };
  // Server sentences with a name or number inside (llm/__init__.py, core/admin.py).
  const PATTERNS = [
    [/^(.+)，但睡着了$/, (m, why) => `${tr(why)}, but she's asleep`],
    [/^不认识的模型提供商 (.+)$/, "unknown provider $1"], [/^(.+) 已停用$/, "$1 is disabled"],
    [/^(.+) 还没有 API key$/, "$1 has no API key yet"], [/^(.+) 还没选模型$/, "$1 has no model chosen"],
    [/^(.+)（(.+)，先用备用）$/, (m, label, why) => `${label} (${tr(why)}; using the backup)`],
    [/^没有编号 (.+) 的请求$/, "no request #$1"], [/^这个请求已经处理过了（(.+)）$/, "already handled ($1)"],
    [/^环境变量 (.+)$/, "env var $1"],
    [/^本机 magpie 网关（需要网关密钥：运行 (.+)）$/, "local magpie gateway (needs its gateway key: run $1)"],
    [/^本机 (.+)（(\d+) 个模型）$/, (m, name, n) => `local ${name === "magpie 网关" ? "magpie gateway" : name} (${n === "1" ? "1 model" : n + " models"})`],
    [/^对应的平台没在运行$/, "that platform isn't running"], [/^平台没接受这个操作（可能请求过期了）$/, "the platform refused (the request may have expired)"],
    [/^已同意：(.+)$/, "Approved: $1"], [/^已拒绝：(.+)$/, "Declined: $1"],
  ];

  const stored = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
  let lang = ["zh", "en"].includes(stored()) ? stored() : /^zh/i.test(navigator.language || "zh") ? "zh" : "en";
  const fill = (s, vars) => vars ? s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m)) : s;
  function t(zh, vars) {
    const en = lang === "en" ? EN[zh] : undefined;
    return typeof en === "function" ? en(vars || {}) : fill(en ?? zh, vars);
  }
  function tr(text) {
    if (lang !== "en" || !text) return text ?? "";
    if (typeof EN[text] === "string") return EN[text];
    for (const [re, to] of PATTERNS) if (re.test(text)) return text.replace(re, to);
    return text;
  }

  // Static markup: translate text nodes and a few attributes in place, remembering the Chinese.
  const ATTRS = ["placeholder", "title", "aria-label"];
  const textZh = new WeakMap(), attrZh = new WeakMap();
  const skip = (el) => el.closest("script, style, textarea, [data-i18n-skip]");
  function swap(original) {
    const key = original.trim();
    if (!key || lang === "zh" || typeof EN[key] !== "string") return original;
    return original.slice(0, original.indexOf(key)) + EN[key] + original.slice(original.indexOf(key) + key.length);
  }
  function translate(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.parentElement || skip(n.parentElement)) continue;
      if (!textZh.has(n)) { if (lang === "zh" || !(n.nodeValue.trim() in EN)) continue; textZh.set(n, n.nodeValue); }
      n.nodeValue = swap(textZh.get(n));
    }
    for (const el of root.querySelectorAll(ATTRS.map((a) => `[${a}]`).join(","))) {
      if (skip(el)) continue;
      const saved = attrZh.get(el) || {};
      for (const a of ATTRS) {
        if (!el.hasAttribute(a)) continue;
        if (!(a in saved)) { if (lang === "zh" || !(el.getAttribute(a).trim() in EN)) continue; saved[a] = el.getAttribute(a); }
        el.setAttribute(a, swap(saved[a]));
      }
      attrZh.set(el, saved);
    }
  }

  // Unsaved form edits survive the re-render a language switch causes: matched by id, else by position.
  const touched = new WeakSet();
  document.addEventListener("input", (e) => touched.add(e.target), true);
  document.addEventListener("change", (e) => touched.add(e.target), true);
  const FIELDS = "input:not([type=file]), textarea, select";
  function snapshot() {
    return [...document.querySelectorAll(FIELDS)].map((el, i) => touched.has(el) && { id: el.id, i, tag: el.tagName, value: el.value, checked: el.checked }).filter(Boolean);
  }
  function restore(saved) {
    for (const s of saved) {
      const el = (s.id && document.getElementById(s.id)) || document.querySelectorAll(FIELDS)[s.i];
      if (!el || el.tagName !== s.tag) continue;
      if (el.type === "checkbox" || el.type === "radio") el.checked = s.checked; else el.value = s.value;
      touched.add(el);
      if (el.tagName === "SELECT") el.dispatchEvent(new Event("change"));
    }
  }

  const listeners = [];
  let zhTitle = null;
  function paint() {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    if (zhTitle === null) zhTitle = document.title;
    document.title = zhTitle.split(" · ").map((p) => t(p)).join(" · ");
    translate(document.body);
    document.querySelectorAll(".lang-toggle").forEach((b) => {
      b.dataset.lang = lang;
      b.setAttribute("aria-label", lang === "zh" ? "Switch to English" : "切换到中文");
      b.title = b.getAttribute("aria-label");
    });
  }
  async function set(next) {
    if (next === lang || !["zh", "en"].includes(next)) return;
    lang = next;
    try { localStorage.setItem(KEY, lang); } catch { /* private window: still switch this page */ }
    const saved = snapshot();
    paint();
    for (const fn of listeners) { try { await fn(lang); } catch (e) { console.error(e); } }
    restore(saved);
  }
  function mount() {
    document.querySelectorAll("[data-lang-slot]").forEach((slot) => {
      if (slot.querySelector(".lang-toggle")) return;
      const b = document.createElement("button");
      b.type = "button"; b.className = "lang-toggle";
      b.innerHTML = '<span data-l="zh">中</span><span data-l="en">EN</span>';
      b.onclick = () => set(lang === "zh" ? "en" : "zh");
      slot.appendChild(b);
    });
    paint();
  }
  window.addEventListener("storage", (e) => { if (e.key === KEY && e.newValue) set(e.newValue); });
  return { t, tr, set, mount, onChange: (fn) => listeners.push(fn), get lang() { return lang; } };
})();
const t = I18N.t, tr = I18N.tr;
