# nonebot-plugin-genshin-cos

基于 NoneBot2 的米游社图片插件，支持原神、崩坏3、星穹铁道、大别野和绝区零。
命令由 [Alconna](https://github.com/nonebot/plugin-alconna) 解析，
数据由 [LocalStore](https://github.com/nonebot/plugin-localstore) 管理，消息使用 OneBot V11。

## 安装

需要 Python 3.10+、NoneBot2 2.4+ 和 OneBot V11 适配器。依赖解析器可能按 Alconna 版本安装更新的 NoneBot2。

```bash
nb plugin install nonebot-plugin-genshin-cos
```

从本地重构源码安装：

```bash
python -m pip install .
```

在机器人项目的 `pyproject.toml` 中启用：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_genshin_cos"]
```

Alconna、LocalStore 和 APScheduler 会自动加载，不需要额外填写到插件列表。

## 使用

命令不需要前缀，也兼容机器人配置的命令前缀，例如 `/热门cos 原神 x3`。
原有的 `coser`、`cos图` 后缀及游戏别名继续可用。
数量支持 `3`、`x3`、`X3`、`*3`，超过 `cos_max` 时取上限；零、负数和非整数会提示错误。

| 命令 | 示例 | 权限 |
| --- | --- | --- |
| 热门cos | `热门cos 原神 x3` | 所有人 |
| 最新cos | `最新cos 崩铁 x2` | 所有人 |
| 日榜cos / 周榜cos / 月榜cos | `周榜cos 原神 x3` | 所有人 |
| 精品cos | `精品cos 绝区零 x2` | 所有人 |
| 搜索cos | `搜索cos 原神 甘雨 x3` | 所有人 |
| 原有搜索格式 | `搜索原神cos甘雨 x3` | 所有人 |
| 下载cos / 保存cos / cos保存 | `下载cos 原神`，省略游戏时会询问 | 超管、群主、管理员 |
| 开启每日推送 | `开启每日推送原神 8:30` | 群内超管、群主、管理员 |
| 关闭每日推送 | `关闭每日推送原神` | 群内超管、群主、管理员 |
| 查看本群推送 / 查看推送 / 查看订阅 | `@机器人 查看本群推送` | 群内所有人 |

搜索词包含空格时使用引号，例如 `搜索cos 原神 "甘雨 cosplay" x2`。
精品图延续原有限制，不支持原神和星穹铁道。
每日推送仍仅支持原神和大别野，时间采用 APScheduler 的时区（默认由宿主系统决定）。
每日推送使用合并转发，图片数量也受 `cos_max` 限制。
新订阅绑定当前机器人，机器人断线时跳过推送；重新开启同一订阅可更新时间。

## 配置

在机器人 `.env` 中按需设置：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| cos_max | int | 10 | 每次最多发送的图片数，范围 1–100 |
| cos_path | str | 空字符串 | 图片保存目录；为空时使用 LocalStore 插件数据目录下的 images |
| cos_cd | int | 10 | 每个机器人下每位用户的请求冷却秒数，0 表示关闭 |
| cos_forward_msg | bool | false | 普通查图是否使用合并转发 |
| cos_delay | float | 0.5 | 普通逐张发送的间隔秒数 |
| cos_timeout | float | 20 | HTTP 请求超时秒数，必须大于 0 |

指定 `cos_path` 时，相对路径以机器人运行目录为基准，绝对路径直接使用。
也可以通过 LocalStore 配置统一修改数据根目录：

```dotenv
LOCALSTORE_USE_CWD=true
COS_MAX=10
COS_CD=10
COS_FORWARD_MSG=false
COS_DELAY=0.5
COS_TIMEOUT=20
```

`LOCALSTORE_USE_CWD=true` 时，本插件数据默认位于运行目录
`data/nonebot_plugin_genshin_cos/`。其他配置方式参考
[LocalStore 文档](https://github.com/nonebot/plugin-localstore#配置项)，
可通过 `nb localstore` 查看目录。

## 从旧版迁移

- Python 最低版本由 3.9 调整为 3.10。
- 首次启动若 LocalStore 中没有 `subscriptions.json`，会读取旧的
  `config/genshincos.json`，校验并转换后写入新位置，旧文件保留。
- 旧订阅缺少机器人 ID，临时使用第一个已连接的 OneBot V11 机器人；
  多机器人环境请由目标机器人重新执行开启命令以绑定。
- 无效或损坏的订阅文件会阻止插件启动，不会静默清空。修正文件后重新启动。
- 旧下载图片不会自动搬移。需要继续使用原目录时设置 `cos_path`。
- 图片按 URL 的 SHA-256 命名，避免查询参数及同名 URL 冲突；已保存文件会跳过。
- 移除了未在插件内使用的同步爬虫接口和全局爬虫实例。直接导入旧爬虫类的外部脚本需要改用 `HoyoClient`。

## 实现与验证

- 一个按需创建、关机关闭的 HTTP 客户端复用连接池。
- 同一榜单一次请求同时获取标题和图片，不重复调用接口。
- 冷却记录使用单调时钟，到期按顺序删除，并每分钟清理空闲记录。
- 图片按 64 KiB 流式写盘，失败继续后续下载，取消时清理临时文件。
- 最多同时处理 4 个图片请求，下载任务单独串行，避免同一文件并发写入。
- 订阅通过临时文件替换保存；写入失败时保留内存和原文件。
- 只保留 `uv.lock` 管理开发依赖；移除了 aiofiles、ujson 和 pathlib 回溯包。

开发与检查：

```bash
uv sync --frozen --group dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

测试覆盖命令实际分发、权限、冷却、订阅迁移、多机器人隔离、接口错误和下载中断。
另在 uv 环境中完成 122 项真实 OneBot V11 WebSocket 黑盒用例、服务重启恢复和实际定时调度验证；
固定数据测试仅替换米游社 HTTP 边界。Matcha 桌面版另行验证了聊天和下载。
真实米游社热门、最新、日周月榜和搜索接口已联调，真实 QQ 平台的风控与展示仍需部署验证。
流式下载降低下载期间的图片缓冲峰值；Alconna 自身也有依赖开销，不代表整个机器人进程常驻内存一定下降。

## 0.4.0 已知限制

- 2026-10-18 联调时，精品图上游 `forumGoodPostFullList` 返回 HTTP 404。
  插件会提示请求失败；固定数据下的精品命令测试通过不代表线上接口可用。
- Matcha 0.4.8 未实现发送合并转发扩展 API。合并转发与每日推送需使用支持
  `send_group_forward_msg` / `send_private_forward_msg` 的 OneBot 实现。

版本变更与发布校验方式见 [CHANGELOG.md](https://github.com/Cvandia/nonebot-plugin-genshin-cos/blob/main/CHANGELOG.md)。

图片版权归原作者所有，请尊重 coser 的创作权。

## License

[MIT](LICENSE)
