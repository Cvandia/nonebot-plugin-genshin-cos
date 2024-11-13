from random import choice

from nonebot import get_bot, get_driver
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, MessageSegment
from nonebot.params import ArgPlainText, CommandArg, RegexGroup
from nonebot.plugin import on_command, on_regex, require
from nonebot.rule import to_me

from .hoyospider import *
from .utils import *

require("nonebot_plugin_apscheduler")

try:
    import ujson as json
except ModuleNotFoundError:
    import json

import asyncio
import random
import re

from nonebot_plugin_apscheduler import scheduler

# 用户cd数据
user_data = {}
CONFIG: dict[str, dict[str, str]] = {
    "原神": {},
    "崩坏3": {},
    "大别野": {},
    "星穹铁道": {},
}
DRIVER = get_driver()

# 读取配置文件
config_path = Path("config/genshincos.json")
config_path.parent.mkdir(parents=True, exist_ok=True)
if config_path.exists():
    with open(config_path, "r", encoding="utf8") as f:
        CONFIG = json.load(f)
else:
    with open(config_path, "w", encoding="utf8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=4)

# 事件响应器
download_cos = on_command(
    "下载cos",
    aliases={"cos保存", "保存cos"},
    block=False,
    priority=5,
    permission=SUPER_PERMISSION,
)
hot_cos = on_command(
    "热门cos", aliases={"热门coser", "热门cos图"}, block=False, priority=5
)
rank_cos = on_regex(
    r"^(日|月|周)榜cos[r]?[图]?(.+)?", priority=5, block=False, flags=re.I
)
latest_cos = on_command(
    "最新cos", aliases={"最新coser", "最新cos图"}, block=False, priority=5
)
good_cos = on_command(
    "精品cos", aliases={"精品coser", "精品cos图"}, block=False, priority=5
)
search_cos = on_regex(
    r"^搜索(原神|崩坏3|星穹铁道|大别野|绝区零)cos[r]?[图]?(.+)?",
    block=False,
    priority=5,
)
turn_aps = on_regex(
    r"^(开启|关闭)每日推送(原神|崩坏3|星穹铁道|大别野)(\s)?(.+)?",
    block=False,
    priority=5,
    flags=re.I,
    permission=SUPER_PERMISSION,
)
show_aps = on_command(
    "查看本群推送",
    aliases={"查看推送", "查看订阅"},
    block=False,
    priority=5,
    rule=to_me(),
)


@search_cos.handle()
async def _(
    bot: Bot,
    matcher: Matcher,
    event: MessageEvent,
    args: tuple[str, ...] = RegexGroup(),
):
    if not args[1]:
        await search_cos.finish("请指定搜索内容")
    else:
        groups = args[1].split()

    forum_type_map = {
        "原神": ForumType.GenshinCos,
        "崩坏3": ForumType.Honkai3rdPic,
        "大别野": ForumType.DBYCOS,
        "星穹铁道": ForumType.StarRailCos,
        "绝区零": ForumType.ZZZ,
    }

    search_class = forum_type_map.get(args[0])
    if not search_class:
        await search_cos.finish("暂不支持该类型")

    search_instance = Search(search_class, groups[0])
    await send_images(bot, matcher, groups, event, search_instance)


async def handle_cos_type(arg: str, finish_func, send_func, type_dict: dict):
    if not arg:
        await finish_func("请指定cos类型")
    args = arg.split()
    send_type = type_dict.get(args[0])
    if not send_type:
        await finish_func("暂不支持该类型")
    await send_func(args, send_type)


@hot_cos.handle()
async def _(
    bot: Bot, matcher: Matcher, event: MessageEvent, arg: Message = CommandArg()
):
    type_dict = {
        **{name: genshin_hot for name in GENSHIN_NAME},
        **{name: honkai3rd_hot for name in HONKAI3RD_NAME},
        **{name: dbycos_hot for name in DBY_NAME},
        **{name: starrail_hot for name in STAR_RAIL},
        **{name: zzz_hot for name in ZZZ_NAME},
    }
    await handle_cos_type(
        arg.extract_plain_text(),
        hot_cos.finish,
        lambda args, send_type: send_images(bot, matcher, args, event, send_type),
        type_dict,
    )


@rank_cos.handle()
async def _(
    bot: Bot,
    matcher: Matcher,
    event: MessageEvent,
    group: tuple[str, ...] = RegexGroup(),
):
    if not group[1]:
        await rank_cos.finish("请指定cos类型")
    args = group[1].split()
    rank_type = {
        "日": RankType.Daily,
        "周": RankType.Weekly,
        "月": RankType.Monthly,
    }.get(group[0])
    type_dict = {
        **{name: Rank(ForumType.GenshinCos, rank_type) for name in GENSHIN_NAME},
        **{name: Rank(ForumType.DBYCOS, rank_type) for name in DBY_NAME},
    }
    await handle_cos_type(
        group[1],
        rank_cos.finish,
        lambda args, send_type: send_images(bot, matcher, args, event, send_type),
        type_dict,
    )


@latest_cos.handle()
async def _(
    bot: Bot, matcher: Matcher, event: MessageEvent, arg: Message = CommandArg()
):
    type_dict = {
        **{name: genshin_latest_comment for name in GENSHIN_NAME},
        **{name: honkai3rd_latest_comment for name in HONKAI3RD_NAME},
        **{name: dbycos_latest_comment for name in DBY_NAME},
        **{name: starrail_latest_comment for name in STAR_RAIL},
        **{name: zzz_latest_comment for name in ZZZ_NAME},
    }
    await handle_cos_type(
        arg.extract_plain_text(),
        latest_cos.finish,
        lambda args, send_type: send_images(bot, matcher, args, event, send_type),
        type_dict,
    )


@good_cos.handle()
async def _(
    bot: Bot, matcher: Matcher, event: MessageEvent, arg: Message = CommandArg()
):
    if not arg:
        await good_cos.finish("请指定cos类型")
    args = arg.extract_plain_text().split()
    if args[0] in GENSHIN_NAME:
        await good_cos.finish("原神暂不支持精品cos")
    elif args[0] in STAR_RAIL:
        await good_cos.finish("星穹铁道暂不支持精品cos")
    type_dict = {
        **{name: honkai3rd_good for name in HONKAI3RD_NAME},
        **{name: dbycos_good for name in DBY_NAME},
        **{name: zzz_good for name in ZZZ_NAME},
    }
    await handle_cos_type(
        arg.extract_plain_text(),
        good_cos.finish,
        lambda args, send_type: send_images(bot, matcher, args, event, send_type),
        type_dict,
    )


@show_aps.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    send_msg = "本群订阅的推送有:\n"
    for game_type, dict in CONFIG.items():
        if game_type:
            for group_id, time in dict.items():
                if str(event.group_id) == group_id:
                    send_msg += f"{game_type}的每日{time}推送\n"
    await show_aps.finish(send_msg)


@turn_aps.handle()
async def _(event: GroupMessageEvent, args: tuple[str, ...] = RegexGroup()):
    if scheduler is None:
        await turn_aps.finish("未安装apscheduler插件,无法使用此功能")

    mode, game_type, time = args[0], args[1], args[3]
    if game_type not in GENSHIN_NAME + DBY_NAME:
        await turn_aps.finish("暂不支持其他类型的订阅，仅支持原神和大别野")

    aps_group_id = str(event.group_id)
    if mode == "开启":
        if not time:
            await turn_aps.finish("请指定推送时间")
        if aps_group_id in CONFIG.get(game_type, {}):
            await turn_aps.finish("该群已开启,无需重复开启")

        CONFIG.setdefault(game_type, {})[aps_group_id] = time
        try:
            scheduler.add_job(
                aps_send,
                trigger="cron",
                hour=time.split(":")[0],
                minute=time.split(":")[1],
                id=f"{game_type}{aps_group_id}",
                args=(aps_group_id,),
            )
            logger.debug(f"已成功添加{aps_group_id}的{game_type}定时推送")
        except Exception as e:
            logger.error(e)
    else:
        if aps_group_id not in CONFIG.get(game_type, {}):
            await turn_aps.finish("该群已关闭,无需重复关闭")

        CONFIG[game_type].pop(aps_group_id, None)
        try:
            scheduler.remove_job(f"{game_type}{aps_group_id}")
        except Exception as e:
            logger.error(e)

    with open(config_path, "w", encoding="utf8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=4)

    await turn_aps.finish(f"已成功{mode}{aps_group_id}的{game_type}定时推送")


@download_cos.got(
    "game_type", prompt="你想下载哪种类型的,有原神和大别野,崩坏3,星穹铁道"
)
async def got_type(game_type: str = ArgPlainText()):
    type_dict = {
        **{name: genshin_hot for name in GENSHIN_NAME},
        **{name: dbycos_hot for name in DBY_NAME},
        **{name: honkai3rd_hot for name in HONKAI3RD_NAME},
        **{name: starrail_hot for name in STAR_RAIL},
        **{name: zzz_hot for name in ZZZ_NAME},
    }
    hot = type_dict.get(game_type)
    if not hot:
        await download_cos.finish("暂不支持该类型")
    image_urls = await hot.async_get_urls()
    if not image_urls:
        await download_cos.finish(f"没有找到{game_type}的cos图片")
    else:
        await download_cos.send(f"正在下载{game_type}的cos图片")
        try:
            await download_from_urls(image_urls, SAVE_PATH / f"{game_type}cos")
            await download_cos.finish(
                f"已成功保存{len(image_urls)}张{game_type}的cos图片"
            )
        except WriteError as e:
            await download_cos.finish(f"保存部分{game_type}的cos图片失败,原因:{e}")


###########################################################################################


# 定时任务
async def aps_send(aps_goup_id: str):
    logger.debug("正在发送定时推送")
    bot: Bot = get_bot()  # type:ignore
    for game_type, dict in CONFIG.items():
        if not game_type:
            continue
        for saved_group_id, time in dict.items():
            if not (
                datetime.now().hour == int(time.split(":")[0])
                and datetime.now().minute == int(time.split(":")[1])
            ):
                continue
            if saved_group_id != aps_goup_id:
                continue
            try:
                group_id = int(saved_group_id)
                send_type = {
                    **{name: genshin_rank_daily for name in GENSHIN_NAME},
                    **{name: dbycos_rank_daily for name in DBY_NAME},
                }.get(game_type)
                if not send_type:
                    continue
                image_list = await send_type.async_get_urls(page_size=5)
                name_list = await send_type.async_get_name(page_size=5)
                rank_text = "\n".join(
                    [f"{i + 1}.{name}" for i, name in enumerate(name_list)]
                )
                msg_list = [
                    MessageSegment.text(f"✅米游社{game_type}cos每日榜单✅"),
                    MessageSegment.text(rank_text),
                ] + [MessageSegment.image(img) for img in image_list]
                msg_list = msglist2forward("米游社cos", "2854196306", msg_list)
                await bot.call_api(
                    "send_group_forward_msg", group_id=group_id, messages=msg_list
                )
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(e)


async def send_images(
    bot: Bot,
    matcher: Matcher,
    args: list,
    event: MessageEvent,
    send_type: HoyoBasicSpider,
):
    """
    发送图片

    params:
        bot: 当前bot
        matcher: 事件响应器
        args: 命令参数(0:类型 1:数量)
        event: 消息事件类型
        send_type: 爬虫类型
    """
    global user_data
    out_cd, deletime, user_data = check_cd(event.user_id, user_data)
    if not out_cd:
        await matcher.finish(f"cd冷却中,还剩{deletime}秒", at_sender=True)
        return

    num_images = min(int(re.sub(r"[x|*|X]", "", args[1])) if len(args) > 1 else 1, MAX)

    await matcher.send(
        f"获取{num_images}张图片中…请稍等" if num_images > 1 else "获取图片中…请稍等"
    )

    try:
        image_list = await send_type.async_get_urls()
        if num_images > len(image_list):
            await matcher.finish(f"最多只能获取{len(image_list)}张图片", at_sender=True)
            return

        selected_images = (
            random.sample(image_list, num_images)
            if num_images > 1
            else [choice(image_list)]
        )
        msg_list = (
            [MessageSegment.text(f"✅找到最新的一些{args[0]}图如下:✅")]
            if num_images > 1
            else []
        )

        for img in selected_images:
            msg_list.append(MessageSegment.image(img))

        if IS_FORWARD:
            await send_forward_msg(bot, event, "米游社cos", bot.self_id, msg_list)
        else:
            await send_regular_msg(matcher, msg_list)
    except ActionFailed:
        await matcher.finish("账户风控了,发送不了图片", at_sender=True)


@DRIVER.on_startup
async def start_aps():
    try:
        if scheduler == None:
            logger.error("未安装apscheduler插件,无法使用此功能")
        with open(config_path, "r", encoding="utf8") as f:
            CONFIG: dict[str, dict[str, str]] = json.load(f)
        for game_type, _dict in CONFIG.items():
            if game_type == "":
                continue
            for aps_group_id, time in _dict.items():
                if time == "":
                    continue
                try:
                    if scheduler:
                        scheduler.add_job(
                            aps_send,
                            trigger="cron",
                            hour=time.split(":")[0],
                            minute=time.split(":")[1],
                            id=f"{game_type}{aps_group_id}",
                            args=(aps_group_id,),
                        )
                    else:
                        logger.error("未安装apscheduler插件,无法使用此功能")
                        return
                    logger.debug(f"已成功添加{aps_group_id}的{game_type}定时推送")
                except Exception as e:
                    logger.error(e)
                    continue
    except Exception as e:
        logger.error(e)
