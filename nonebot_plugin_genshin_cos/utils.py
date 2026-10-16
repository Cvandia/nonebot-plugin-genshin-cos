from __future__ import annotations

import math
from collections import OrderedDict
from time import monotonic


class Cooldown:
    """Expiry-ordered cooldowns, pruned on access and periodically by the plugin."""

    def __init__(self, seconds: int):
        self.seconds = seconds
        self.users: OrderedDict[tuple[str, int], float] = OrderedDict()

    def prune(self) -> None:
        now = monotonic()
        while self.users:
            key, expiry = next(iter(self.users.items()))
            if expiry > now:
                break
            del self.users[key]

    def acquire(self, bot_id: str, user_id: int) -> int:
        self.prune()
        if not self.seconds:
            return 0
        key = (bot_id, user_id)
        now = monotonic()
        if key in self.users:
            return max(1, math.ceil(self.users[key] - now))
        self.users[key] = now + self.seconds
        return 0


def parse_count(value: str, maximum: int) -> int:
    raw = value[1:] if value.startswith(("x", "X", "*")) else value
    if not raw.isascii() or not raw.isdecimal() or int(raw) < 1:
        raise ValueError("图片数量必须是正整数，例如 x3")
    return min(int(raw), maximum)


def parse_time(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2 or any(not p.isascii() or not p.isdecimal() for p in parts):  # noqa: PLR2004
        raise ValueError("时间格式应为 HH:MM，例如 08:30")
    hour, minute = map(int, parts)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):  # noqa: PLR2004
        raise ValueError("时间必须在 00:00 到 23:59 之间")
    return hour, minute
