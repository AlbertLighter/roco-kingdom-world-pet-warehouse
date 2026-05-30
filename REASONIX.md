# REASONIX.md — Roco Kingdom World Pet Warehouse

Reasonix 会话自动加载的知识库。上限 80 行。

## 技术栈

- **语言**: Python ≥3.12（`.python-version`, `pyproject.toml`）
- **框架**: FastAPI（uvicorn ASGI 服务器）
- **数据库**: SQLite（`warehouse.db`，直接使用 `sqlite3` 模块，无 ORM）
- **前端**: 原生 JS + HTML5 + CSS3（无框架/打包工具）
- **核心依赖**: `fastapi`, `uvicorn`, `requests`, `python-dotenv`, `mwclient`
- **包管理器**: `uv`（仓库包含 `uv.lock`）

## 目录结构

| 路径 | 说明 |
|------|------|
| `backend/` | FastAPI 服务端（`main.py` — 488 行单文件 API） |
| `frontend/` | 静态 Web UI：`index.html`, `breeding.html`, `app.js`, `breeding.js`, `style.css` |
| `scripts/` | 数据同步工具：`fetcher.py`（同步流水线）, `api_client.py`（HTTP 客户端） |
| `docs/` | 游戏配置 JSON（`egg.json`, `PETBASE_CONF.json`）、算法文档、图片 |
| `roco_kingdom_world_conf/` | 698 个游戏数据 JSON 文件（Git 子模块，只读参考数据） |
| `test_wiki.py` | 独立 Wiki 抓取测试（使用 `mwclient`） |

## 常用命令

| 操作 | 命令 |
|------|------|
| 同步游戏数据 | `python scripts/fetcher.py` |
| 启动后端 | `python backend/main.py`（监听 `0.0.0.0:8000`） |
| 安装依赖 | `uv sync`（或 `pip install -r requirements.txt`） |
| 初始化子模块（首次 clone） | `git submodule update --init` |
| 更新子模块 | `./scripts/sync_conf.sh` |

未配置测试框架、linter 或格式化工具（未发现 ruff/flake8/pytest 等配置）。

## 约定

- **注释**: `backend/main.py` 和 `scripts/` 中全部使用中文注释。
- **密钥**: `.env` 文件存放 `AUTHORIZATION_TOKEN`, `OPENID`, `ACCESS_TOKEN`, `REFRESH_TOKEN`。`.env.example` 作为模板提交到仓库。
- **CORS**: FastAPI 中间件使用全开配置（`allow_origins=["*"]`）。
- **提交风格**: 中英文混合的祈使句信息，**不是** Conventional Commits 格式。
- **前端**: 全局 JS 函数 + DOM 查询，无模块系统。

## 注意点

- **`warehouse.db`** — 运行时创建的 SQLite 数据库。在 `.gitignore` 中（匹配 `*.db`）。删除即可重置所有同步数据。
- **`docs/` JSON 文件** — 游戏参考配置，**非**可编辑源码。`egg.json` 映射宠物 ID → 蛋组；`PETBASE_CONF.json` 定义宠物基础属性。
- **`roco_kingdom_world_conf/`** — Git 子模块，指向 `github.com/mieli1722/roco_kingdom_world_conf.git`。请勿手动编辑。
  - 首次 clone：`git submodule update --init`
  - 更新到最新：`./scripts/sync_conf.sh` 或 `git submodule update --remote`
- **`.env`** — 包含真实认证令牌。**切勿提交。** `.env.example` 是安全模板。
- **后端为单文件** — `backend/main.py` 约 488 行。后续重构可能会拆分。
