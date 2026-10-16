import pytest

from nonebot_plugin_genshin_cos import matcher as handlers
from nonebot_plugin_genshin_cos.utils import parse_count, parse_time


@pytest.mark.parametrize("kind", ["热门", "最新", "精品", "日榜", "周榜", "月榜"])
@pytest.mark.parametrize("suffix", ["cos", "coser", "cos图"])
def test_image_commands(kind, suffix):
    result = handlers.image_matchers[kind].command().parse(f"{kind}{suffix} 原神 x3")
    assert result.matched
    assert result.all_matched_args == {"game": "原神", "count": "x3"}


@pytest.mark.parametrize(
    "message", ["搜索原神cos甘雨 x3", "搜索原神cos图 甘雨 x3", "搜索cos 原神 甘雨 x3"]
)
def test_search_legacy_and_new(message):
    result = handlers.search.command().parse(message)
    assert result.matched
    assert result.all_matched_args == {"game": "原神", "keyword": "甘雨", "count": "x3"}


@pytest.mark.parametrize("enabled", [True, False])
def test_compact_subscriptions(enabled):
    matcher = handlers.enable_push if enabled else handlers.disable_push
    message = "开启每日推送原神 8:30" if enabled else "关闭每日推送原神"
    result = matcher.command().parse(message)
    assert result.matched
    assert result.all_matched_args["game"] == "原神"


@pytest.mark.parametrize(
    "value", ["0", "-1", "x0", "xx3", "abc", "1.5", "３", "x", "*-3"]
)
def test_invalid_counts(value):
    with pytest.raises(ValueError, match="图片数量"):
        parse_count(value, 10)


@pytest.mark.parametrize("value", ["3", "x3", "X3", "*3"])
def test_valid_count(value):
    assert parse_count(value, 10) == 3
    assert parse_count("x999", 10) == 10


@pytest.mark.parametrize("value", ["25:00", "8:60", "12", "x:1", "-1:30", "８:３０"])
def test_invalid_time(value):
    with pytest.raises(ValueError, match="时间"):
        parse_time(value)


def test_time():
    assert parse_time("8:30") == (8, 30)


@pytest.mark.parametrize(
    "message",
    ["/热门cos 原神 x3", "/热门coser 原神 x3", "日榜cos原神 x3", "日榜COS原神 x3"],
)
def test_prefix_and_compact_compatibility(message):
    kind = "热门" if "热门" in message else "日榜"
    result = handlers.image_matchers[kind].command().parse(message)
    assert result.matched
    assert result.all_matched_args == {"game": "原神", "count": "x3"}
