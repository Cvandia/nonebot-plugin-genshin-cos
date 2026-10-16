import tempfile
from pathlib import Path

import nonebot
from nonebot.adapters.onebot.v11 import Adapter

runtime = tempfile.TemporaryDirectory(prefix="genshin-cos-tests-")
root = Path(runtime.name)
nonebot.init(
    driver="~fastapi",
    localstore_data_dir=str(root / "data"),
    localstore_config_dir=str(root / "config"),
    localstore_cache_dir=str(root / "cache"),
)
nonebot.get_driver().register_adapter(Adapter)
if nonebot.load_plugin("nonebot_plugin_genshin_cos") is None:
    raise RuntimeError("Failed to load nonebot_plugin_genshin_cos for tests")
