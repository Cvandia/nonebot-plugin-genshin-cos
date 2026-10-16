from __future__ import annotations

import asyncio
import random
from functools import lru_cache
from pathlib import Path

import httpx
from arclet.alconna import Alconna, Args, CommandMeta
from nonebot import get_bots, get_driver, logger
from nonebot.adapters.onebot.v11 import (
    GROUP_ADMIN,
    GROUP_OWNER,
    ActionFailed,
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.matcher import (
    Matcher,  # noqa: TC002 - NoneBot resolves annotations at runtime
)
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot_plugin_alconna import Arparma, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_localstore import get_plugin_data_dir, get_plugin_data_file

from .config import config
from .hoyospider import HoyoClient, MiyousheError, game_name, image_urls
from .storage import Subscription, Subscriptions
from .utils import Cooldown, parse_count, parse_time

driver = get_driver()
subscriptions = Subscriptions(get_plugin_data_file("subscriptions.json"))
save_path = (
    Path(config.cos_path).expanduser()
    if config.cos_path
    else get_plugin_data_dir() / "images"
)
cooldown = Cooldown(config.cos_cd)
# Bound expensive work before fetching lists or opening download streams.
request_lock = asyncio.Semaphore(4)
download_lock = asyncio.Lock()
ADMIN = SUPERUSER | GROUP_ADMIN | GROUP_OWNER


@lru_cache(maxsize=1)
def get_client() -> HoyoClient:
    return HoyoClient(config.cos_timeout)


def forward_nodes(bot: Bot, messages: list) -> list[dict]:
    return [
        {
            "type": "node",
            "data": {"name": "米游社cos", "uin": bot.self_id, "content": message},
        }
        for message in messages
    ]


async def send_messages(bot: Bot, event: MessageEvent, messages: list) -> None:
    if config.cos_forward_msg:
        target = (
            {"group_id": event.group_id}
            if isinstance(event, GroupMessageEvent)
            else {"user_id": event.user_id}
        )
        api = (
            "send_group_forward_msg"
            if isinstance(event, GroupMessageEvent)
            else "send_private_forward_msg"
        )
        await bot.call_api(api, **target, messages=forward_nodes(bot, messages))
    else:
        for index, message in enumerate(messages):
            if index:
                await asyncio.sleep(config.cos_delay)
            await bot.send(event, message)


def make_command(name: str, args=None, *, aliases=(), permission=None, rule=None):
    return on_alconna(
        Alconna(
            list(dict.fromkeys(["", *driver.config.command_start])),
            name,
            args or Args(),
            meta=CommandMeta(compact=False),
        ),
        aliases=set(aliases),
        use_cmd_start=False,
        auto_send_output=True,
        priority=5,
        block=True,
        permission=permission,
        rule=rule,
    )


def register_images(kind: str):
    matcher = make_command(
        f"{kind}cos",
        Args["game", str, ""]["count", str, "x1"],
        aliases=(f"{kind}coser", f"{kind}cos图"),
    )
    matcher.shortcut(
        rf"(?i:{kind}cos(?:er|图)?)",
        {"command": f"{kind}cos", "fuzzy": True},
    )

    @matcher.handle()
    async def handle(bot: Bot, event: MessageEvent, matcher: Matcher, result: Arparma):
        await query_images(bot, event, matcher, result, kind)

    return matcher


async def query_images(
    bot: Bot,
    event: MessageEvent,
    matcher: Matcher,
    result: Arparma,
    kind: str,
) -> None:
    try:
        game = game_name(result.all_matched_args.get("game", ""))
        count = parse_count(result.all_matched_args.get("count", "x1"), config.cos_max)
        keyword = result.all_matched_args.get("keyword", "")
        if kind == "搜索" and not keyword.strip():
            raise ValueError("请指定搜索内容")  # noqa: TRY301
        if kind == "精品" and game in {"原神", "星穹铁道"}:
            raise ValueError(f"{game}暂不支持精品cos")  # noqa: TRY301
    except ValueError as exc:
        await matcher.finish(str(exc))
    remaining = cooldown.acquire(bot.self_id, event.user_id)
    if remaining:
        await matcher.finish(f"冷却中，还剩{remaining}秒", at_sender=True)
    try:
        async with request_lock:
            posts = await get_client().fetch(game, kind, keyword)
            urls = image_urls(posts)
            if not urls:
                await matcher.finish("没有找到相关图片")
            if count > len(urls):
                await matcher.finish(f"最多只能获取{len(urls)}张图片")
            selected = random.sample(urls, count)
            await send_messages(
                bot, event, [MessageSegment.image(url) for url in selected]
            )
    except (httpx.HTTPError, MiyousheError) as exc:
        logger.warning(f"米游社图片获取失败: {exc}")
        await matcher.finish("米游社请求失败，请稍后重试")
    except ActionFailed:
        await matcher.finish("图片发送失败，请稍后重试或切换合并转发模式")


image_matchers = {
    kind: register_images(kind)
    for kind in ("热门", "最新", "精品", "日榜", "周榜", "月榜")
}
search = make_command(
    "搜索cos", Args["game", str]["keyword", str, ""]["count", str, "x1"]
)
search.shortcut(
    r"搜索(原神|崩坏3|星穹铁道|大别野|绝区零)cos(?:er|图)?",
    {"command": "搜索cos", "args": ["{0}"], "fuzzy": True},
)


@search.handle()
async def search_images(
    bot: Bot, event: MessageEvent, matcher: Matcher, result: Arparma
):
    await query_images(bot, event, matcher, result, "搜索")


download = make_command(
    "下载cos",
    Args["game", str, ""],
    aliases=("cos保存", "保存cos"),
    permission=ADMIN,
)


@download.handle()
async def download_images(matcher: Matcher, result: Arparma):
    game = result.all_matched_args.get("game", "")
    if game:
        matcher.set_arg("game", Message(game))


@download.got(
    "game", prompt="你想下载哪种类型：原神、大别野、崩坏3、星穹铁道或绝区零？"
)
async def save_images(matcher: Matcher):
    try:
        game = game_name(str(matcher.get_arg("game")))
    except ValueError as exc:
        await matcher.finish(str(exc))
    if download_lock.locked():
        await matcher.finish("已有下载任务进行中，请稍后重试")
    try:
        async with download_lock, request_lock:
            urls = image_urls(await get_client().fetch(game))
            if not urls:
                await matcher.finish("没有找到相关图片")
            await matcher.send(f"正在保存{len(urls)}张{game}图片")
            success, failed = await get_client().download(
                urls, save_path / f"{game}cos"
            )
    except (httpx.HTTPError, MiyousheError, OSError) as exc:
        logger.warning(f"米游社下载失败: {exc}")
        await matcher.finish("下载失败，请检查网络和存储目录")
    await matcher.finish(f"保存完成：成功{success}张，失败{failed}张")


async def push(row: Subscription) -> None:
    bots = get_bots()
    bot = (
        bots.get(row.bot_id)
        if row.bot_id
        else next((b for b in bots.values() if isinstance(b, Bot)), None)
    )
    if not isinstance(bot, Bot):
        logger.warning(f"跳过每日推送：机器人 {row.bot_id or '旧配置未绑定'} 未连接")
        return
    try:
        async with request_lock:
            posts = await get_client().fetch(row.game, "日榜", page_size=5)
            urls = image_urls(posts)[: config.cos_max]
            if not urls:
                return
            titles = "\n".join(f"{i}. {post.title}" for i, post in enumerate(posts, 1))
            messages = [MessageSegment.text(f"米游社{row.game}cos每日榜单\n{titles}")]
            messages.extend(MessageSegment.image(url) for url in urls)
            await bot.call_api(
                "send_group_forward_msg",
                group_id=row.group_id,
                messages=forward_nodes(bot, messages),
            )
    except (httpx.HTTPError, MiyousheError, ActionFailed) as exc:
        logger.warning(f"每日推送失败 {row.key}: {exc}")


def job_id(row: Subscription) -> str:
    return f"genshin_cos:{row.key}"


def add_job(row: Subscription) -> None:
    hour, minute = parse_time(row.time)
    scheduler.add_job(
        push,
        "cron",
        hour=hour,
        minute=minute,
        id=job_id(row),
        args=(row,),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )


def register_subscription(enabled: bool):
    name = "开启" if enabled else "关闭"
    matcher = make_command(
        f"{name}每日推送",
        Args["game", str]["time", str, ""],
        permission=ADMIN,
    )
    matcher.shortcut(
        f"{name}每日推送",
        {"command": f"{name}每日推送", "fuzzy": True},
    )

    @matcher.handle()
    async def change(bot: Bot, event: GroupMessageEvent, result: Arparma):
        try:
            game = game_name(result.all_matched_args["game"])
            if game not in {"原神", "大别野"}:
                raise ValueError("每日榜单推送仅支持原神和大别野")  # noqa: TRY301
            value = result.all_matched_args.get("time", "")
            hour, minute = parse_time(value) if enabled else (0, 0)
            row = Subscription(
                bot.self_id, event.group_id, game, f"{hour:02}:{minute:02}"
            )
            removed = await subscriptions.update(row, enabled)
        except (ValueError, OSError) as exc:
            await matcher.finish(f"订阅更新失败：{exc}")
        for old in removed:
            if scheduler.get_job(job_id(old)):
                scheduler.remove_job(job_id(old))
        if enabled:
            add_job(row)
        await matcher.finish(
            f"已{name}{game}每日推送" + (f"（{row.time}）" if enabled else "")
        )

    return matcher


enable_push = register_subscription(True)
disable_push = register_subscription(False)
show_push = make_command("查看本群推送", aliases=("查看推送", "查看订阅"), rule=to_me())


@show_push.handle()
async def show_subscriptions(bot: Bot, event: GroupMessageEvent):
    rows = [
        f"{row.game}：每天 {row.time}"
        for row in subscriptions.items.values()
        if row.group_id == event.group_id and row.bot_id in {"", bot.self_id}
    ]
    await show_push.finish(
        "本群订阅：\n" + "\n".join(rows) if rows else "本群尚未开启推送"
    )


@driver.on_startup
async def startup():
    # Do not swallow corrupt subscription files and later overwrite them.
    await subscriptions.load(Path("config/genshincos.json"))
    for row in subscriptions.items.values():
        add_job(row)
    scheduler.add_job(
        prune_cooldowns,
        "interval",
        seconds=60,
        id="genshin_cos:cooldown",
        replace_existing=True,
        max_instances=1,
    )


async def prune_cooldowns():
    # Async jobs run on the event loop, alongside cooldown.acquire().
    cooldown.prune()


@driver.on_shutdown
async def shutdown():
    for job in scheduler.get_jobs():
        if job.id.startswith("genshin_cos:"):
            scheduler.remove_job(job.id)
    if get_client.cache_info().currsize:
        await get_client().close()
        get_client.cache_clear()
