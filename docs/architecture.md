# 项目架构

> 洛克王国：世界 宠物仓库 — 技术架构概述

---

## 整体架构图

```
浏览器  仓库 / 繁育 / 放生 / 抓包
   │  HTTP、SSE
   ▼
backend/main.py
   │
   ├── warehouse.db          精灵、盒子、大世界队伍
   ├── roco_kingdom_world_conf/   只读游戏配置
   │
   ├── 同步精灵  scripts/fetcher.py ──► 游戏 HTTP 接口（需要 .env）
   │
   └── 改道记录  scripts/game_relay.py
                 本机观察 NRC 的 TCP 8195，原样转发
                 解密后写入 captures/packets.db
                 精灵列表、登录盒子、换盒、进化、孵蛋、捕捉写入 warehouse.db
```

---

## 目录结构

```
roco-kingdom-world-pet-warehouse/
├── backend/main.py            # FastAPI 接口
├── frontend/
│   ├── index.html             # 仓库
│   ├── breeding.html          # 繁育
│   ├── release.html           # 放生推荐
│   ├── packets.html           # 抓包记录
│   └── style.css
├── scripts/
│   ├── fetcher.py             # HTTP 同步
│   ├── api_client.py
│   ├── game_relay.py          # 8195 改道与解密
│   ├── capture_sync.py        # 精灵列表和会话内更新
│   ├── packet_store.py        # captures/packets.db
│   ├── pet_boxes.py           # 盒子位置、放生、赠送
│   ├── world_teams.py
│   ├── game_release_click.py  # 只点击本机游戏窗口
│   └── box_overlay.py         # 置顶对照窗
├── docs/                      # 字段、算法、接口
├── roco_kingdom_world_conf/   # 游戏配置子模块
├── warehouse.db               # 运行生成，已 gitignore
├── .env.example
├── pyproject.toml
└── uv.lock
```

---

## 数据流

### 同步流程 (Sync)

HTTP 同步和改道抓包最后都调用 `mark_absent_inactive`：名单里没有、且 `world_team` 为空的在库精灵才标成已放生。列表没拿全时两条路都不标。

```
fetcher.py
  1. 检查登录、刷新时间
  2. /api/pet/list 分页
  3. 补全 pet_base_info
  4. 标记已放生（跳过大世界队伍）
  5. /api/pet/detail 写入 pet_instances
```

HTTP 同步不写 `box_id`。盒子来自登录包和游戏内换盒。

### 会话内更新

改道记录在精灵列表之外还处理这些下行：

| 消息 | 作用 |
|------|------|
| `0x0102` 登录 | 大世界三队；认全至少 3 个盒子后才刷新这些盒子的格子 |
| `0x1891` 整理 | 同一套盒子规则 |
| `0x1888` 换盒 | 只改回包里点名的格子 |
| `0x01AE` 进化、`0x141E` 换牌 | 用包里的 PetData 更新这一只 |
| `0x030C` 孵蛋、`0x0243` 奖励、`0x1983` 捕捉 | 写入新精灵；能对上编号时顺便落盒 |
| `0x132C` 战斗结束 | 只收入手时间就在附近的精灵 |
| `0x01C5` 放生、`0x1808` 赠送确认 | 标成不在库。带完整精灵数据的赠送包是预览，不改库 |

登录或整理若认不出足够的盒子，原来的格子保持不动。

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
