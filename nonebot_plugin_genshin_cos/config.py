from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class Config(BaseModel):
    cos_max: int = Field(default=10, ge=1, le=100)
    cos_path: str = ""
    cos_cd: int = Field(default=10, ge=0)
    cos_forward_msg: bool = False
    cos_delay: float = Field(default=0.5, ge=0)
    cos_timeout: float = Field(default=20, gt=0)


config = get_plugin_config(Config)
