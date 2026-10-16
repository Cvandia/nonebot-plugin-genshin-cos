from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_apscheduler")

__plugin_meta__ = PluginMetadata(
    name="米游社cos",
    description="获取米游社 cos 图片、搜索、下载及每日榜单推送",
    usage="热门cos 原神 x3；搜索原神cos 甘雨；开启每日推送原神 8:30",
    type="application",
    homepage="https://github.com/Cvandia/nonebot-plugin-genshin-cos",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

from . import matcher as matcher
