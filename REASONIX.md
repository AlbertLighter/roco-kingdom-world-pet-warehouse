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
| `scripts/capture_sync.py` | 精灵列表，以及换盒、进化、孵蛋、捕捉 |
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

Windows 用 `start.bat`（纯 ASCII、CRLF，会申请管理员权限）。服务只监听 127.0.0.1。

## 约定

- 注释用中文。提交说明用中文，不是 Conventional Commits。
- `.env` 只放令牌，模板是 `.env.example`。
- 改抓包、解密或前端后要重启进程。
- 完整名单才会把缺席精灵标成已放生，并且跳过 `world_team` 非空的精灵。
- 登录或整理至少认出 3 个可信盒子才改格子；没认出的盒子保持原位。`0x1888` 只改点名的那几只。

## 数据

- `warehouse.db`、`captures/`、`logs/` 都在 `.gitignore`。
- 解密消息在 `captures/packets.db`，会话密钥在 `captures/keys/latest.key`。
- 服务地址是 http://localhost:8000 。
