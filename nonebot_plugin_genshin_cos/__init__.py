from nonebot import logger
import contextlib
from . import matcher

with contextlib.suppress(Exception):
    from nonebot.plugin import PluginMetadata

    __plugin_meta__ = PluginMetadata(
        name="米游社cos",
        description="获取原神coser图片",
        usage="原神cos,CosPlus,下载cos",
        type="application",
        homepage="https://github.com/Cvandia/nonebot_plugin-genshin-cos",
        supported_adapters={"~onebot.v11"},
        extra={
            "unique_name": "genshin_cos",
            "example": "保存cos:保存cos图片至本地文件",
            "author": "nor",
            "version": "0.3.3",
        },
    )


logo = """<g>
 /$$      /$$ /$$ /$$   /$$         /$$     /$$               /$$$$$$                     
| $$$    /$$$|__/| $$  | $$        |  $$   /$$/              /$$__  $$                    
| $$$$  /$$$$ /$$| $$  | $$  /$$$$$$\  $$ /$$//$$$$$$       | $$  \__/  /$$$$$$   /$$$$$$$
| $$ $$/$$ $$| $$| $$$$$$$$ /$$__  $$\  $$$$//$$__  $$      | $$       /$$__  $$ /$$_____/
| $$  $$$| $$| $$| $$__  $$| $$  \ $$ \  $$/| $$  \ $$      | $$      | $$  \ $$|  $$$$$$ 
| $$\  $ | $$| $$| $$  | $$| $$  | $$  | $$ | $$  | $$      | $$    $$| $$  | $$ \____  $$
| $$ \/  | $$| $$| $$  | $$|  $$$$$$/  | $$ |  $$$$$$/      |  $$$$$$/|  $$$$$$/ /$$$$$$$/
|__/     |__/|__/|__/  |__/ \______/   |__/  \______/        \______/  \______/ |_______/ 
</g>"""

logger.opt(colors=True).info(logo)
