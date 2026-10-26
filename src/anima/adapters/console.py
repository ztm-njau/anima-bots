"""Chat with the bot in the terminal. Handy over SSH or when you don't want a browser."""

from __future__ import annotations

import asyncio
import uuid

from rich.console import Console

from anima.adapters.base import Adapter
from anima.core.events import Bubble, Chat, Incoming, Sender

PRIVATE = Chat("console", "private", "you", "你")
GROUP = Chat("console", "group", "demo", "终端群")

HELP = """[dim]命令：/group 群聊模式  /private 私聊模式  /as 名字 换个身份（群聊）  /poke 戳她
      /time +8 时间旅行（小时）  /wake 叫醒她  /fast 快进开关  /state 看她的状态
      /plan 重新安排今天  /diary 现在写日记  /quit 退出[/dim]"""


class ConsoleAdapter(Adapter):
    platform = "console"
    capabilities = frozenset({"poke"})

    def __init__(self) -> None:
        super().__init__()
        self.console = Console()
        self.chat = PRIVATE
        self.speaker = "你"

    async def send(self, chat: Chat, bubble: Bubble, quote: str | None = None) -> str | None:
        assert self.brain is not None
        name = self.brain.cfg.identity.display_name
        if bubble.voice:
            self.console.print(f"[bold red]{name}[/] › 🎤 [italic]{bubble.voice}[/]")
        else:
            text = "".join(
                s.value if s.type == "text" else self.brain.stickers.emoji(s.value) for s in bubble.segments
            )
            self.console.print(f"[bold red]{name}[/] › {text}")
        return uuid.uuid4().hex[:8]

    async def poke(self, chat: Chat, user_id: str) -> None:
        assert self.brain is not None
        self.console.print(f"[yellow]👉 {self.brain.cfg.identity.display_name} 戳了戳你[/]")

    async def repl(self, runtime) -> None:
        brain = runtime.brain
        name = brain.cfg.identity.display_name
        life = brain.life()
        self.console.print(f"[bold]和{name}聊天[/]  北京时间 {brain.clock.now():%H:%M}，她现在：{life.activity}")
        if life.asleep:
            self.console.print("[dim]（她睡着了，消息会等她醒来再回。输入 /wake 叫醒她）[/]")
        self.console.print(HELP)
        while True:
            try:
                line = await asyncio.to_thread(input, "")
            except (EOFError, KeyboardInterrupt):
                return
            line = line.strip()
            if not line:
                continue
            if line.startswith("/"):
                if await self._command(line, runtime) is False:
                    return
                continue
            await brain.handle(Incoming(
                self.chat, Sender(f"cli-{self.speaker}", self.speaker), line,
                message_id=uuid.uuid4().hex[:8], mentions_me=f"@{name}" in line,
            ))

    async def _command(self, line: str, runtime) -> bool | None:
        brain = runtime.brain
        cmd, _, arg = line.partition(" ")
        if cmd == "/quit":
            return False
        if cmd == "/group":
            self.chat, self.speaker = GROUP, arg or "小鱼"
            self.console.print(f"[dim]群聊模式，你现在是「{self.speaker}」[/]")
        elif cmd == "/private":
            self.chat, self.speaker = PRIVATE, "你"
            self.console.print("[dim]私聊模式[/]")
        elif cmd == "/as":
            self.speaker = arg or self.speaker
            self.console.print(f"[dim]你现在是「{self.speaker}」[/]")
        elif cmd == "/poke":
            await brain.handle(Incoming(self.chat, Sender(f"cli-{self.speaker}", self.speaker), "", kind="poke", mentions_me=True))
        elif cmd == "/time":
            brain.clock.set_offset_hours(float(arg or 0))
            await runtime.life.tick()
            self.console.print(f"[dim]现在是北京时间 {brain.clock.now():%H:%M}，她：{brain.life().activity}[/]")
        elif cmd == "/wake":
            from anima.web import wake_offset

            brain.clock.set_offset_hours(wake_offset(brain.clock, 20))
            await runtime.life.tick()
            self.console.print(f"[dim]北京时间 {brain.clock.now():%H:%M}，她醒着[/]")
        elif cmd == "/fast":
            brain.humanizer.scale = 0.0 if brain.humanizer.scale else 1.0
            self.console.print(f"[dim]{'快进' if brain.humanizer.scale == 0 else '真人节奏'}[/]")
        elif cmd == "/state":
            life = brain.life()
            plan = await brain.memory.journal_get(brain.clock.today(), "plan")
            self.console.print(f"[dim]{brain.clock.describe()} · {life.activity} · {brain.mood.describe(life.energy)}\n今天：{plan or '还没安排'}\n花费：{brain.cost_text()} · 模型：{brain.llm.label} {brain.llm.model}[/]")
        elif cmd == "/plan":
            self.console.print(f"[dim]{await runtime.life.plan_day(brain.clock.today())}[/]")
        elif cmd == "/diary":
            self.console.print(f"[dim]{await runtime.life.write_diary(brain.clock.today()) or '（没写出来）'}[/]")
        else:
            self.console.print(HELP)
        return None
