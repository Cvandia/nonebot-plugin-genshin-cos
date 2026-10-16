"""One asynchronous client for all supported Miyoushe image endpoints."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlsplit

import anyio
import httpx


class Game(NamedTuple):
    gids: int
    forum_id: int
    aliases: tuple[str, ...]


GAMES = {
    "原神": Game(2, 49, ("OP", "欧泡", "⭕", "🅾️", "🅾️P", "原", "圆")),
    "崩坏3": Game(1, 4, ("崩崩崩", "蹦蹦蹦", "崩坏三", "崩三", "崩崩崩三", "崩坏3rd")),
    "大别野": Game(5, 47, ("DBY",)),
    "星穹铁道": Game(6, 62, ("星穹", "崩铁", "铁道", "星铁", "穹p", "穹铁")),
    "绝区零": Game(8, 65, ("绝零区", "绝零", "0", "零", "绝区", "0区")),
}
GAME_ALIASES = {
    alias.casefold(): name
    for name, game in GAMES.items()
    for alias in (name, *game.aliases)
}
RANKS = {"日榜": 1, "周榜": 2, "月榜": 3}


def game_name(value: str) -> str:
    try:
        return GAME_ALIASES[value.casefold()]
    except KeyError:
        raise ValueError(
            "暂不支持该游戏，请使用原神、崩坏3、大别野、星穹铁道或绝区零"
        ) from None


class Post(NamedTuple):
    title: str
    images: tuple[str, ...]


class MiyousheError(Exception):
    """An unsuccessful or malformed Miyoushe response."""


class HoyoClient:
    def __init__(self, timeout: float = 20, transport=None):
        self.client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://bbs.mihoyo.com/"},
            transport=transport,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch(
        self, game: str, kind: str = "热门", keyword: str = "", page_size: int = 20
    ) -> list[Post]:
        info = GAMES[game]
        params = {"forum_id": info.forum_id, "page_size": page_size}
        key = "list"
        if kind in RANKS:
            endpoint = "getImagePostList"
            params.update(gids=info.gids, type=RANKS[kind])
        elif kind == "搜索":
            endpoint, key = "searchPosts", "posts"
            params = {
                "gids": info.gids,
                "forum_id": info.forum_id,
                "size": page_size,
                "keyword": keyword,
            }
        elif kind == "精品":
            if game in {"原神", "星穹铁道"}:
                raise ValueError(f"{game}暂不支持精品cos")
            endpoint, key = "forumGoodPostFullList", "posts"
            params["gids"] = info.gids
        elif kind in {"热门", "最新"}:
            endpoint = "getForumPostList"
            params.update({"is_hot": True} if kind == "热门" else {"sort_type": 1})
        else:
            raise ValueError("不支持的榜单类型")
        response = await self.client.get(
            f"https://bbs-api.mihoyo.com/post/wapi/{endpoint}", params=params
        )
        response.raise_for_status()
        try:
            payload = response.json()
            if payload.get("retcode", 0) != 0:
                raise MiyousheError(str(payload.get("message", "接口返回错误")))
            return [
                Post(
                    str(item["post"].get("subject", "")), tuple(item["post"]["images"])
                )
                for item in payload["data"][key]
            ]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise MiyousheError("米游社返回了无效的帖子数据") from exc

    async def download(self, urls: list[str], directory: Path) -> tuple[int, int]:
        """Download sequentially in 64 KiB chunks; never retain whole images in RAM."""
        await anyio.Path(directory).mkdir(parents=True, exist_ok=True)
        success = failed = 0
        for url in urls:
            suffix = Path(urlsplit(url).path).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                suffix = ".jpg"
            target = directory / (hashlib.sha256(url.encode()).hexdigest() + suffix)
            temporary = anyio.Path(target.with_suffix(target.suffix + ".part"))
            try:
                if await anyio.Path(target).exists():
                    success += 1
                    continue
                async with self.client.stream("GET", url) as response:
                    response.raise_for_status()
                    async with await temporary.open("wb") as stream:
                        async for chunk in response.aiter_bytes(65536):
                            await stream.write(chunk)
                await temporary.replace(target)
                success += 1
            except (httpx.HTTPError, OSError):
                failed += 1
            finally:
                # Shield cleanup so cancellation cannot leave partial files behind.
                with anyio.CancelScope(shield=True):
                    await temporary.unlink(missing_ok=True)
        return success, failed


def image_urls(posts: list[Post]) -> list[str]:
    return list(dict.fromkeys(url for post in posts for url in post.images))
