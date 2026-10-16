from inspect import iscoroutinefunction
from itertools import count
from unittest.mock import AsyncMock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent
from nonebot.message import handle_event

from nonebot_plugin_genshin_cos import matcher as handlers
from nonebot_plugin_genshin_cos.hoyospider import Post
from nonebot_plugin_genshin_cos.storage import Subscription, Subscriptions

message_ids = count(1)


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    bot = Bot(Adapter(nonebot.get_driver()), "10000")
    sent = []

    async def send(_bot, event, message, **_kwargs):  # noqa: ARG001
        sent.append(str(message))

    async def call_api(_bot, api, **kwargs):
        sent.append((api, kwargs))
        return {}

    monkeypatch.setattr(Bot, "send", send)
    monkeypatch.setattr(Bot, "call_api", call_api)
    client = AsyncMock()
    client.fetch.return_value = [
        Post("标题", ("https://example.org/a.jpg", "https://example.org/b.jpg"))
    ]
    client.download.return_value = (2, 0)
    monkeypatch.setattr(handlers, "get_client", lambda: client)
    monkeypatch.setattr(
        handlers, "subscriptions", Subscriptions(tmp_path / "subscriptions.json")
    )
    handlers.cooldown.users.clear()
    yield bot, client, sent
    for job in handlers.scheduler.get_jobs():
        if job.id.startswith("genshin_cos:"):
            handlers.scheduler.remove_job(job.id)


def event(message, role="member"):
    return GroupMessageEvent(
        time=0,
        self_id=10000,
        post_type="message",
        sub_type="normal",
        message_type="group",
        message_id=next(message_ids),
        group_id=123,
        user_id=456,
        message=message,
        original_message=message,
        raw_message=message,
        font=0,
        sender={"user_id": 456, "nickname": "tester", "role": role},
        to_me=True,
    )


async def test_real_command_dispatch_and_cooldown(runtime):
    bot, client, sent = runtime
    await handle_event(bot, event("热门cos 原神 x2"))
    client.fetch.assert_awaited_once_with("原神", "热门", "")
    assert len(sent) == 2
    await handle_event(bot, event("热门cos 原神"))
    assert "冷却" in sent[-1]
    assert client.fetch.await_count == 1


async def test_invalid_count_does_not_request(runtime):
    bot, client, sent = runtime
    await handle_event(bot, event("热门cos 原神 x0"))
    client.fetch.assert_not_awaited()
    assert "正整数" in sent[-1]


async def test_legacy_search_dispatch(runtime):
    bot, client, sent = runtime
    await handle_event(bot, event("搜索原神cos甘雨 x2"))
    client.fetch.assert_awaited_once_with("原神", "搜索", "甘雨")
    assert len(sent) == 2


async def test_download_permission_and_argument(runtime):
    bot, client, sent = runtime
    await handle_event(bot, event("下载cos 原神"))
    client.download.assert_not_awaited()
    await handle_event(bot, event("下载cos 原神", "admin"))
    client.download.assert_awaited_once()
    assert "成功2张" in sent[-1]


async def test_download_interactive_prompt(runtime):
    bot, client, sent = runtime
    await handle_event(bot, event("下载cos", "admin"))
    assert "哪种类型" in sent[-1]
    client.download.assert_not_awaited()
    await handle_event(bot, event("原神", "admin"))
    client.download.assert_awaited_once()
    assert "成功2张" in sent[-1]


async def test_invalid_subscription_leaves_no_job_or_data(runtime):
    bot, _client, sent = runtime
    await handle_event(bot, event("开启每日推送原神 25:00", "admin"))
    assert "订阅更新失败" in sent[-1]
    assert not handlers.subscriptions.items
    assert not handlers.scheduler.get_jobs()


async def test_subscribe_permission(runtime):
    bot, _client, sent = runtime
    await handle_event(bot, event("开启每日推送原神 8:30"))
    assert not sent
    assert not handlers.subscriptions.items


async def test_subscribe_and_disable_dispatch(runtime):
    bot, _client, sent = runtime
    await handle_event(bot, event("开启每日推送原神 8:30", "admin"))
    row = Subscription("10000", 123, "原神", "08:30")
    assert handlers.subscriptions.items == {row.key: row}
    job = handlers.scheduler.get_job(handlers.job_id(row))
    assert job.args == (row,)
    await handle_event(bot, event("关闭每日推送原神", "admin"))
    assert not handlers.subscriptions.items
    assert handlers.scheduler.get_job(handlers.job_id(row)) is None
    assert "已关闭" in sent[-1]


async def test_push_fetches_once_and_routes_exact_game(runtime, monkeypatch):
    bot, client, sent = runtime
    monkeypatch.setattr(handlers, "get_bots", lambda: {bot.self_id: bot})
    await handlers.push(Subscription(bot.self_id, 123, "大别野", "08:30"))
    client.fetch.assert_awaited_once_with("大别野", "日榜", page_size=5)
    api, arguments = sent[-1]
    assert api == "send_group_forward_msg"
    assert arguments["group_id"] == 123
    assert "标题" in str(arguments["messages"])


async def test_startup_restores_jobs_and_cleans_cooldowns_on_event_loop(
    runtime, monkeypatch, tmp_path
):
    bot, _client, _sent = runtime
    monkeypatch.chdir(tmp_path)
    row = Subscription(bot.self_id, 123, "原神", "08:30")
    await handlers.subscriptions.update(row, True)
    handlers.subscriptions.items.clear()
    await handlers.startup()
    assert handlers.scheduler.get_job(handlers.job_id(row)).args == (row,)
    job = handlers.scheduler.get_job("genshin_cos:cooldown")
    assert iscoroutinefunction(job.func)
    handlers.cooldown.users[(bot.self_id, 456)] = 0
    await job.func()
    assert not handlers.cooldown.users
