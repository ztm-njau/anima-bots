"""How long to wait before treating a burst of messages as finished.

A fixed timer either answers "在吗" before the real question arrives or leaves a finished
question hanging. Instead the wait reads the last message: a line that trails off ("然后，"
"那个" a bare @) earns more time, a clear question or a closing sticker earns less, and someone
typing in quick bursts gets a wait that follows their own rhythm.
"""

from __future__ import annotations

import re

from anima.config import BehaviorConfig
from anima.core.events import Incoming

_TRAILING = re.compile(r"(?:[，,、：:；;]|\.\.\.|…+|——|然后|就是|那个|还有|而且|但是|不过|因为|所以|结果|比如|我想|我觉得|话说|对了)\s*$")
_OPENERS = re.compile(r"^(?:在吗|在不在|在嘛|在？|在\?|hello|hi|嗨|哈喽|你好|问你个事|问个问题|跟你说|和你说|我跟你讲|有个事|emmm*|额+|呃+)[\s？?。.!！~～]*$", re.I)
_DONE = re.compile(r"(?:[？?！!。]|吗|呢|吧|啊|呀|哈哈+|嘿嘿|晚安|拜拜|好的|谢谢)\s*$")


def unfinished(ev: Incoming, my_name: str = "") -> bool:
    """Whether this message looks like more is coming."""
    text = ev.text.strip()
    if my_name:
        text = text.replace(f"@{my_name}", "").strip()
    if ev.kind != "message":
        return False
    if not text:
        return not ev.images or ev.mentions_me  # a bare @, or a picture that usually gets explained next
    if ev.images and not ev.meta.get("sticker") and len(text) <= 4:
        return True
    return bool(_TRAILING.search(text) or _OPENERS.match(text))


def finished(ev: Incoming) -> bool:
    if ev.meta.get("sticker") and not ev.text.replace("[表情包]", "").strip():
        return True  # a sticker after some lines usually closes the thought
    return bool(_DONE.search(ev.text.strip()))


def settle_wait(batch: list[Incoming], cfg: BehaviorConfig, private: bool, my_name: str = "") -> float:
    """Seconds to keep waiting after the latest message in ``batch``."""
    if not batch:
        return 0.0
    base = cfg.debounce_private if private else cfg.debounce_group
    last = batch[-1]
    if last.kind == "poke":
        return min(base, 1.5)
    wait = base
    if unfinished(last, my_name):
        wait += cfg.debounce_unfinished
    elif finished(last):
        wait *= 0.6
    # Follow the sender's own rhythm: if they have been sending every 3 s, give them about that.
    mine = [ev.timestamp for ev in batch if ev.sender.id == last.sender.id]
    if len(mine) >= 2:
        gaps = [b - a for a, b in zip(mine, mine[1:], strict=False) if 0 < b - a < 30]
        if gaps:
            wait = max(wait, min(sum(gaps) / len(gaps) * 1.4, base * 2.5))
    return wait
