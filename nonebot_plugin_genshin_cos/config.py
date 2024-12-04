from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    cos_max: int = 10
    cos_path: str = ""
    cos_cd: int = 10
    cos_forward_msg: bool = False
    cos_delay: float = 0.5


config = get_plugin_config(Config)
