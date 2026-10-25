"""Douyin live rooms, through a real Chrome window (experimental).

Douyin has no public API for personal accounts, so she sits in live rooms like a viewer:
a persistent Chrome profile (log in once with ``anima login douyin``), a MutationObserver
that forwards new chat lines, and the room's own input box for replies.

Douyin's markup changes often. Selectors live in ``bot.toml`` under
``[platforms.douyin.selectors]`` so they can be fixed without touching code.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel

from anima.adapters.base import Adapter
from anima.core.events import Bubble, Chat, Incoming, Sender

DEFAULT_SELECTORS = {
    "item": "[class*='webcast-chatroom___item']",
    "name": "[class*='nickname'], [class*='webcast-chatroom___nickname']",
    "content": "[class*='content-with-emoji-text'], [class*='webcast-chatroom___content']",
    "input": "textarea[class*='webcast-chatroom___textarea'], [class*='chat-input'] textarea, [contenteditable='true']",
}

OBSERVER_JS = """
(sel) => {
  if (window.__animaObserver) return;
  const seen = new WeakSet();
  const read = (node) => {
    if (!(node instanceof HTMLElement)) return;
    const items = node.matches(sel.item) ? [node] : node.querySelectorAll(sel.item);
    for (const item of items) {
      if (seen.has(item)) continue;
      seen.add(item);
      const name = item.querySelector(sel.name)?.innerText?.trim().replace(/[:：]$/, '') || '';
      const content = item.querySelector(sel.content)?.innerText?.trim() || '';
      if (name && content) window.__animaDanmaku(JSON.stringify({name, content}));
    }
  };
  window.__animaObserver = new MutationObserver((muts) => muts.forEach(m => m.addedNodes.forEach(read)));
  window.__animaObserver.observe(document.body, {childList: true, subtree: true});
}
"""


class DouyinConfig(BaseModel):
    enabled: bool = False
    live_rooms: list[str | int] = []
    headless: bool = False
    nickname: str = ""  # her Douyin nickname, so she can ignore her own lines
    selectors: dict[str, str] = {}


def profile_dir(data_dir: Path) -> Path:
    path = data_dir / "browser" / "douyin"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def interactive_login(data_dir: Path, wait_seconds: float = 300) -> bool:
    """Open Chrome on douyin.com and wait for a QR login. The profile keeps the session."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(profile_dir(data_dir)), channel="chrome", headless=False)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.douyin.com/")
        print("在打开的 Chrome 窗口里扫码登录抖音（建议用给可乐准备的账号），登录后会自动保存。")
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            cookies = {c["name"] for c in await ctx.cookies("https://www.douyin.com")}
            if "sessionid" in cookies or "sessionid_ss" in cookies:
                print("登录成功，已保存。")
                await ctx.close()
                return True
            await asyncio.sleep(2)
        await ctx.close()
        return False


class DouyinAdapter(Adapter):
    platform = "douyin"

    def __init__(self, cfg: dict[str, Any], data_dir: Path):
        super().__init__()
        self.cfg = DouyinConfig.model_validate(cfg)
        self.selectors = {**DEFAULT_SELECTORS, **self.cfg.selectors}
        self.data_dir = data_dir
        self._pw = None
        self._ctx = None
        self._pages: dict[str, Any] = {}
        self._task: asyncio.Task | None = None

    async def start(self, brain) -> None:
        await super().start(brain)
        if not self.cfg.live_rooms:
            logger.info("[douyin] no live rooms configured")
            return
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            str(profile_dir(self.data_dir)), channel="chrome", headless=self.cfg.headless,
            viewport={"width": 1280, "height": 860},
        )
        for room in self.cfg.live_rooms:
            await self._join(str(room))

    async def _join(self, room: str) -> None:
        page = await self._ctx.new_page()

        async def on_line(payload: str) -> None:
            data = json.loads(payload)
            if self.cfg.nickname and data["name"] == self.cfg.nickname:
                return
            assert self.brain is not None
            alias = self.brain.cfg.identity.display_name
            await self.brain.handle(Incoming(
                chat=Chat("douyin", "live", room, f"抖音直播间 {room}"),
                sender=Sender(f"dy:{data['name']}", data["name"]),
                text=data["content"],
                kind="danmaku",
                mentions_me=alias in data["content"],
            ))

        await page.expose_function("__animaDanmaku", on_line)
        await page.goto(f"https://live.douyin.com/{room}", wait_until="domcontentloaded")
        await asyncio.sleep(5)
        await page.evaluate(OBSERVER_JS, self.selectors)
        self._pages[room] = page
        logger.info("[douyin] joined live room {}", room)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._ctx:
            await self._ctx.close()
        if self._pw:
            await self._pw.stop()

    def can_speak(self, chat: Chat) -> bool:
        return chat.id in self._pages

    async def send(self, chat: Chat, bubble: Bubble, quote: str | None = None) -> str | None:
        page = self._pages.get(chat.id)
        text = "".join(s.value for s in bubble.segments if s.type == "text")[:30]
        if not page or not text:
            return None
        box = page.locator(self.selectors["input"]).first
        await box.click()
        await page.keyboard.type(text, delay=random.randint(60, 140))  # human typing cadence
        await asyncio.sleep(random.uniform(0.2, 0.6))
        await page.keyboard.press("Enter")
        return None
