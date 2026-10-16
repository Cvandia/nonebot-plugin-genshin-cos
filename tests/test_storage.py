import json

import pytest

from nonebot_plugin_genshin_cos.storage import Subscription, Subscriptions
from nonebot_plugin_genshin_cos.utils import Cooldown


async def test_migration_and_reload(tmp_path):
    legacy = tmp_path / "genshincos.json"
    legacy.write_text(
        json.dumps({"原神": {"123": "8:30"}, "大别野": {}, "": {}}), encoding="utf-8"
    )
    store = Subscriptions(tmp_path / "new" / "subscriptions.json")
    await store.load(legacy)
    old = Subscription("", 123, "原神", "08:30")
    assert store.items == {old.key: old}
    assert legacy.exists()
    row = Subscription("456", 123, "原神", "09:00")
    assert await store.update(row, True) == [old]
    restored = Subscriptions(store.path)
    await restored.load(legacy)
    assert restored.items == {row.key: row}
    await restored.update(row, False)
    assert restored.items == {}
    assert json.loads(store.path.read_text(encoding="utf-8")) == []


async def test_corrupt_data_is_not_overwritten(tmp_path):
    path = tmp_path / "subscriptions.json"
    path.write_text("{broken", encoding="utf-8")
    store = Subscriptions(path)
    with pytest.raises(ValueError, match="property name"):
        await store.load(tmp_path / "legacy.json")
    assert path.read_text(encoding="utf-8") == "{broken"


async def test_failed_save_keeps_memory_and_file(tmp_path, monkeypatch):
    store = Subscriptions(tmp_path / "subscriptions.json")
    first = Subscription("1", 123, "原神", "08:00")
    await store.update(first, True)
    before = store.path.read_bytes()

    def fail(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(store, "_write", fail)
    with pytest.raises(OSError, match="disk full"):
        await store.update(first._replace(time="09:00"), True)
    assert store.items == {first.key: first}
    assert store.path.read_bytes() == before


async def test_bot_isolation(tmp_path):
    store = Subscriptions(tmp_path / "subscriptions.json")
    first = Subscription("1", 123, "原神", "08:00")
    second = first._replace(bot_id="2")
    await store.update(first, True)
    await store.update(second, True)
    await store.update(first, False)
    assert store.items == {second.key: second}


def test_cooldown_expires_and_isolates_bots(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("nonebot_plugin_genshin_cos.utils.monotonic", lambda: clock[0])
    cooldown = Cooldown(10)
    assert cooldown.acquire("1", 123) == 0
    assert cooldown.acquire("1", 123) == 10
    assert cooldown.acquire("2", 123) == 0
    clock[0] += 11
    cooldown.prune()
    assert not cooldown.users
    assert cooldown.acquire("1", 123) == 0


def test_no_cooldown_does_not_retain_users():
    cooldown = Cooldown(0)
    assert cooldown.acquire("1", 123) == 0
    assert cooldown.users == {}
