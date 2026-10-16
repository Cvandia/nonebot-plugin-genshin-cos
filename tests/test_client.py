import asyncio

import httpx
import pytest

from nonebot_plugin_genshin_cos.hoyospider import (
    HoyoClient,
    MiyousheError,
    game_name,
    image_urls,
)


@pytest.mark.parametrize(
    ("kind", "game", "endpoint", "key", "extra"),
    [
        ("热门", "原神", "getForumPostList", "list", {"is_hot": "true"}),
        ("最新", "原神", "getForumPostList", "list", {"sort_type": "1"}),
        ("日榜", "原神", "getImagePostList", "list", {"type": "1", "gids": "2"}),
        ("周榜", "大别野", "getImagePostList", "list", {"type": "2", "gids": "5"}),
        ("月榜", "原神", "getImagePostList", "list", {"type": "3"}),
        ("精品", "崩坏3", "forumGoodPostFullList", "posts", {"gids": "1"}),
        ("搜索", "星穹铁道", "searchPosts", "posts", {"keyword": "甘雨", "size": "20"}),
    ],
)
async def test_endpoints(kind, game, endpoint, key, extra):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.path.endswith(endpoint)
        for name, value in extra.items():
            assert request.url.params[name] == value
        return httpx.Response(
            200,
            json={
                "retcode": 0,
                "data": {
                    key: [
                        {
                            "post": {
                                "subject": "标题",
                                "images": [
                                    "https://example.org/a.jpg",
                                    "https://example.org/a.jpg",
                                ],
                            }
                        }
                    ]
                },
            },
        )

    client = HoyoClient(transport=httpx.MockTransport(respond))
    try:
        posts = await client.fetch(game, kind, "甘雨")
        assert posts[0].title == "标题"
        assert image_urls(posts) == ["https://example.org/a.jpg"]
        assert len(calls) == 1
    finally:
        await client.close()
    assert client.client.is_closed


@pytest.mark.parametrize(
    "body", [{"retcode": -1, "message": "blocked"}, {"data": {}}, {"data": None}, []]
)
async def test_api_errors(body):
    client = HoyoClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    )
    try:
        with pytest.raises(MiyousheError):
            await client.fetch("原神")
    finally:
        await client.close()


class ChunkStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        for _ in range(4):
            yield b"a" * 65536


async def test_streaming_download_and_skip(tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.path == "/bad.jpg":
            return httpx.Response(404)
        return httpx.Response(200, stream=ChunkStream())

    client = HoyoClient(transport=httpx.MockTransport(respond))
    urls = [
        "https://example.org/good.jpg?x=1",
        "https://example.org/bad.jpg",
        "https://example.org/last.jpg",
    ]
    try:
        assert await client.download(urls, tmp_path) == (2, 1)
        assert len(list(tmp_path.glob("*.jpg"))) == 2
        assert all(path.stat().st_size == 4 * 65536 for path in tmp_path.iterdir())
        assert not list(tmp_path.glob("*.part"))
        assert await client.download(urls[:1], tmp_path) == (1, 0)
        assert len(calls) == 3
    finally:
        await client.close()


class BrokenStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"partial"
        raise httpx.ReadError("connection lost")


async def test_partial_download_removed(tmp_path):
    client = HoyoClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=BrokenStream())
        )
    )
    try:
        assert await client.download(["https://example.org/a.jpg"], tmp_path) == (0, 1)
        assert not list(tmp_path.iterdir())
    finally:
        await client.close()


class CancelledStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"partial"
        raise asyncio.CancelledError


async def test_cancelled_download_removed(tmp_path):
    client = HoyoClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=CancelledStream())
        )
    )
    try:
        with pytest.raises(asyncio.CancelledError):
            await client.download(["https://example.org/a.jpg"], tmp_path)
        assert not list(tmp_path.iterdir())
    finally:
        await client.close()


@pytest.mark.parametrize(
    ("alias", "expected"),
    [("op", "原神"), ("崩坏3RD", "崩坏3"), ("dby", "大别野"), ("崩铁", "星穹铁道")],
)
def test_aliases(alias, expected):
    assert game_name(alias) == expected
