"""Validated subscriptions with atomic writes and legacy migration."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, NamedTuple

import anyio

from .hoyospider import game_name
from .utils import parse_time

if TYPE_CHECKING:
    from pathlib import Path


class Subscription(NamedTuple):
    bot_id: str
    group_id: int
    game: str
    time: str

    @property
    def key(self) -> str:
        return f"{self.bot_id}:{self.group_id}:{self.game}"


class Subscriptions:
    def __init__(self, path: Path):
        self.path = path
        self.items: dict[str, Subscription] = {}
        self.lock = asyncio.Lock()

    async def load(self, legacy: Path) -> None:
        def read():
            if self.path.exists():
                records = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(records, list):
                    raise ValueError("订阅文件应为列表")
                return [Subscription(**row) for row in records], False
            if legacy.exists():
                old = json.loads(legacy.read_text(encoding="utf-8"))
                return [
                    Subscription("", int(group), game_name(game), time)
                    for game, groups in old.items()
                    if game
                    for group, time in groups.items()
                    if time
                ], True
            return [], False

        rows, migrated = await anyio.to_thread.run_sync(read)
        validated = {}
        for row in rows:
            if (
                not isinstance(row.bot_id, str)
                or not isinstance(row.group_id, int)
                or row.group_id <= 0
            ):
                raise ValueError("订阅中的机器人或群号无效")
            hour, minute = parse_time(row.time)
            normalized = row._replace(
                game=game_name(row.game), time=f"{hour:02}:{minute:02}"
            )
            validated[normalized.key] = normalized
        if migrated:
            await anyio.to_thread.run_sync(self._write, validated)
        self.items = validated

    def _write(self, items: dict[str, Subscription]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps(
                    [row._asdict() for row in items.values()],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    async def update(self, row: Subscription, enabled: bool) -> list[Subscription]:
        async with self.lock:
            updated = self.items.copy()
            # Claim legacy subscriptions for the bot issuing this command.
            removed = [
                item
                for item in updated.values()
                if item.group_id == row.group_id
                and item.game == row.game
                and item.bot_id in {"", row.bot_id}
            ]
            for item in removed:
                updated.pop(item.key)
            if enabled:
                updated[row.key] = row
            # Commit memory only after the file has been replaced successfully.
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(self._write, updated)
                self.items = updated
            return removed
