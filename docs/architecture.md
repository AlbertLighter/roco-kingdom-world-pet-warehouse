# 项目架构

> 洛克王国：世界 宠物仓库 — 技术架构概述

---

## 整体架构图

```
┌──────────┐   HTTP/SSE    ┌───────────┐   Game API    ┌──────────────┐
│  前端     │ ◄──────────► │  后端      │ ◄──────────► │  游戏服务器   │
│ (静态页面) │              │ (FastAPI)  │              │ (腾讯网关)    │
│           │              │            │              │              │
│ index.html│   /api/pets  │ main.py    │ gate-way/    │ morefun.game │
│ breeding  │   /api/sync  │ (488行)    │ /api/pet/    │ .qq.com      │
│ .html     │   /api/conf  │            │              │              │
│           │              │            │              │              │
│ app.js    │              │  ┌──────┐  │              │              │
│ breeding  │              │  │ SQLite│  │              │              │
│ .js       │              │  │ware‑  │  │              │              │
│           │              │  │house  │  │              │              │
│ style.css │              │  │ .db   │  │              │              │
└──────────┘              │  └──────┘  │              └──────────────┘
                           └───────────┘
                                   │
                                   │ 读取 (只读)
                                   ▼
                           ┌───────────────┐
                           │ 游戏配置子模块  │
                           │ (Git submodule) │
                           │ roco_kingdom    │
                           │ _world_conf/    │
                           │ 698 个 JSON    │
                           └───────────────┘
```

---

## 目录结构

```
roco-kingdom-world-pet-warehouse/
├── backend/
│   └── main.py              # FastAPI 单文件后端 (~500行)
│
├── frontend/
│   ├── index.html            # 宠物仓库主页
│   ├── breeding.html         # 繁育中心页面
│   ├── app.js                # 仓库页面逻辑
│   ├── breeding.js           # 繁育页面逻辑
│   └── style.css             # 全局样式
│
├── scripts/
│   ├── fetcher.py            # 数据同步脚本（游戏API→SQLite）
│   ├── api_client.py         # 游戏网关 HTTP 客户端
│   └── sync_conf.sh          # 更新子模块的脚本
│
├── docs/
│   ├── api_documentation.md  # API 文档
│   ├── pet_fields.md         # 精灵属性字段说明
│   ├── breed_logic.md        # 繁育算法文档
│   ├── architecture.md       # 本文档
│   ├── index.md              # 文档索引
│   ├── egg.json              # 蛋组配置参考
│   ├── pet_detail_32088.json # API 响应示例
│   └── img/                  # 截图
│
├── roco_kingdom_world_conf/  # Git 子模块（游戏原始配置）
│   ├── PETBASE_CONF.json     # 精灵基础配置
│   ├── PET_BLOOD_CONF.json   # 血脉配置
│   ├── TYPE_DICTIONARY.json  # 系别字典
│   ├── MEDAL_CONF.json       # 奖牌配置
│   ├── SKILL_CONF.json       # 技能配置
│   ├── PET_EGG_CONF.json     # 蛋组配置
│   └── ... (698 个 JSON)
│
├── warehouse.db              # SQLite 数据库（运行生成，已 gitignore）
├── .env                      # 认证令牌（已 gitignore）
├── .env.example              # 环境变量模板
├── pyproject.toml            # 项目配置
├── uv.lock                   # 依赖锁定
└── REASONIX.md               # Reasonix 知识库
```

---

## 数据流

### 同步流程 (Sync)

```
fetcher.py
  1. fetch_user_info()          → 检查登录状态
  2. fetch_refresh_time()       → 获取宠物下次刷新时间
  3. /api/pet/list (分页)       → 获取所有精灵 SerialNum
  4. 补全 pet_base_info         ← PETBASE_CONF.json
  5. 标记已放生精灵             → UPDATE is_active=0
  6. /api/pet/detail (逐只)     → 获取完整详情
  7. INSERT/UPDATE pet_instances
```

### 查询流程 (Query)

```
浏览器 → /api/pets → FastAPI → SQLite ──→ pet_instances JOIN pet_base_info JOIN pet_natures
                               ├── bloodlineMap (PET_BLOOD_CONF.json)
                               ├── typeMap (TYPE_DICTIONARY.json)
                               └── medalMap (MEDAL_CONF.json)
```

### 繁育推荐流程 (Breeding)

```
浏览器 ─→ /api/recommend_parents
         ├── 校验目标精灵 (evolutionStage=1)
         ├── 查询合格母方 (进化链包含目标, gender≠1)
         ├── 查询合格父方 (同蛋组, gender≠2)
         ├── BreedCalculator 概率计算
         │   ├── 属性权重 = 100 + 300×父母本勾选数
         │   ├── 遗传条数概率 (k=2 or 3)
         │   ├── 无放回抽样概率
         │   └── 性格继承概率 (±35%父母 + 30%随机)
         ├── 体型分数 (大块头偏好)
         └── 综合评分排序 Top 10
```

---

## 关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据库 | SQLite (无 ORM) | 单用户工具，零配置，直接 sqlite3 |
| 后端框架 | FastAPI + uvicorn | 异步 SSE 推送同步进度 |
| 前端 | 原生 JS + HTML5 | 无构建工具，零依赖 |
| 认证 | .env 手动配置 | 游戏 API 使用 QQ 直登 fd_token |
| 配置数据 | Git 子模块 | 只读引用，独立更新 |
| 包管理 | uv | 快速，锁定文件 |
