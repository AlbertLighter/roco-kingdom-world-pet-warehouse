# REASONIX.md — Roco Kingdom World Pet Warehouse

## 技术栈

- Python ≥3.12，`uv`，依赖见 `pyproject.toml`
- FastAPI + SQLite（`warehouse.db`，无 ORM）
- 前端：`frontend/` 下仓库、繁育、放生、抓包四个原生页面
- 抓包可选依赖：`uv sync --extra capture`（scapy、pycryptodome、pydivert、psutil、pillow）

## 目录

| 路径 | 说明 |
|------|------|
| `backend/main.py` | HTTP 接口。从项目根目录启动，静态文件按当前目录找 `frontend/` |
| `scripts/fetcher.py` | `.env` 令牌同步。不写盒子 |
| `scripts/game_relay.py` | 本机 8195 改道观察，原样转发 |
| `scripts/capture_sync.py` | 精灵列表、换盒、进化、孵蛋、捕捉，以及仓库快照导入 |
| `scripts/warehouse_push.py` | 收齐分页后推到 `ROCO_CLOUD_URL`，失败可重试 |
| `scripts/capture_divert.py` | Windows 命令行改道，不打开网页 |
| `scripts/pet_boxes.py` | 盒子快照与单次换位 |
| `scripts/world_teams.py` | 登录包里的大世界三队 |
| `scripts/game_release_click.py` | 只点击本机游戏窗口 |
| `roco_kingdom_world_conf/` | 配置子模块，只读 |

## 命令

| 操作 | 命令 |
|------|------|
| 启动 | `uv run python backend/main.py` |
| 安装 | `uv sync`；抓包再加 `--extra capture` |
| 测试 | `uv run python -m unittest discover tests` |
| HTTP 同步 | `uv run python scripts/fetcher.py` |
| 更新子模块 | `./scripts/sync_conf.sh` |

Windows 用 `start.bat`（纯 ASCII、CRLF，会申请管理员权限）。默认只监听 127.0.0.1:8000。`ROCO_HOST` / `ROCO_PORT`（或 `HOST` / `PORT`）可改绑定；`ROCO_CORS_ORIGINS` 追加跨域来源，不接受 `*`。抓包默认只在 Windows 打开（`ROCO_ENABLE_CAPTURE`）。本机用 `ROCO_CLOUD_URL` 和 `ROCO_SYNC_TOKEN` 推送完整仓库，不 scp `warehouse.db`。Ubuntu 部署见 README 和 `deploy/`。

## 约定

- 注释用中文。提交说明用中文，不是 Conventional Commits。
- `.env` 只放令牌，模板是 `.env.example`。
- 改抓包、解密或前端后要重启进程。
- 完整名单才会把缺席精灵标成已放生，并且跳过 `world_team` 非空的精灵。
- 登录或整理至少认出 3 个可信盒子才改格子；没认出的盒子保持原位。`0x1888` 只改点名的那几只。

## 数据

- `warehouse.db`、`captures/`、`logs/` 都在 `.gitignore`。
- 解密消息在 `captures/packets.db`，会话密钥在 `captures/keys/latest.key`。
- 默认服务地址是 http://127.0.0.1:8000 。修改接口仍要 `captures/api.token`，不要为了远程部署放开这个校验。
