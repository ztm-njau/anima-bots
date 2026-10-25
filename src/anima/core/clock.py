"""The bot's sense of time. Offsettable, so the playground can pretend it's 3 a.m."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = "一二三四五六日"


class Clock:
    def __init__(self, timezone: str = "Asia/Shanghai", offset_seconds: float = 0.0):
        self.tz = ZoneInfo(timezone)
        self.offset = offset_seconds

    def now(self) -> datetime:
        return datetime.now(self.tz) + timedelta(seconds=self.offset)

    def timestamp(self) -> float:
        return time.time() + self.offset

    def to_local(self, ts: float) -> datetime:
        return datetime.fromtimestamp(ts, self.tz)

    def today(self) -> str:
        return self.now().strftime("%Y-%m-%d")

    def set_offset_hours(self, hours: float) -> None:
        self.offset = hours * 3600

    def describe(self, when: datetime | None = None) -> str:
        return self.describe_time(when or self.now())

    @staticmethod
    def describe_time(when: datetime) -> str:
        return f"{when:%Y年%m月%d日} 周{WEEKDAYS[when.weekday()]} {when:%H:%M}"

    @staticmethod
    def part_of_day(when: datetime) -> str:
        h = when.hour
        if h < 5:
            return "深夜"
        if h < 8:
            return "清晨"
        if h < 11:
            return "上午"
        if h < 13:
            return "中午"
        if h < 17:
            return "下午"
        if h < 19:
            return "傍晚"
        return "晚上"

    @staticmethod
    def ago(seconds: float) -> str:
        if seconds < 60:
            return "刚刚"
        if seconds < 3600:
            return f"{int(seconds // 60)} 分钟前"
        if seconds < 86400:
            return f"{int(seconds // 3600)} 小时前"
        return f"{int(seconds // 86400)} 天前"
