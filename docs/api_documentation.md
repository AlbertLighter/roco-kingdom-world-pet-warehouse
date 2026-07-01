# 洛克王国：世界 — API 文档

> 本文档包含两部分：游戏服务器 API（抓包分析）和项目自建后端 API。

---

## 一、游戏服务器 API

**网关地址**: `https://morefun.game.qq.com/gw2/gateway/v1/?X-Mcube-Act-Id=E80EH8LJ`
**请求方式**: `POST` (application/x-www-form-urlencoded)
**通用认证**: `authorization` header (JWT Token), `openid`, `area_id=2`, `plat_id=1`

### 1. 宠物实例列表 `/api/pet/list`

分页获取仓库中所有精灵实例。

**请求参数**:
```json
{
  "page": 1,
  "pageSize": 100,
  "searchKeyword": "",
  "manual": false,
  "sort": [{"field": "Count", "order": "desc"}],
  "baseid": ""
}
```

**返回 `data.list[]`**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `SerialNum` | string | 精灵唯一序列号 |
| `PetBaseId` | int | 精灵种类 ID |
| `PetTalentRank` | int | 天赋等级 (1~4) |
| `SpiritLevel` | int | 等级 |
| `PetBlood` | int | 血脉等级 |
| `PetMutation` | int | 变异值 |
| `PetSkillDamType` | int[] | 系别 ID 列表 |

### 2. 精灵详情 `/api/pet/detail`

获取单只精灵的全量数据。

**请求参数**:
```json
{ "id": "10953" }
```

**返回 `data` 字段**:

| 类别 | 字段 | 类型 | 说明 |
|------|------|------|------|
| **基础** | `SerialNum` | string | 精灵序列号 |
| | `PetBaseId` | int | 基础种类 ID |
| | `PetName` | string | 名称，`&` 分隔自定义名 |
| | `SpiritLevel` | int | 等级 |
| | `PetNature` | int | 性格 ID (1~30) |
| | `PetTalentRank` | int | 天赋等级 (1=普通 2=良好 3=优秀 4=极品) |
| | `PetBloodline` | int | 血脉 ID (→PET_BLOOD_CONF.json) |
| | `PetMutation` | int | 变异类型 ID (0=无) |
| | `PetTalentSkill` | int | 天赋技能 ID |
| | `PetSkillDamType` | int[] | 系别 ID 数组 (→TYPE_DICTIONARY.json) |
| **当前属性** | `MaxHp` | int | 生命 |
| | `PhyAttack` | int | 物攻 |
| | `MagAttack` | int | 魔攻 |
| | `PhyDefense` | int | 物防 |
| | `MagDefense` | int | 魔防 |
| | `Speed` | int | 速度 |
| **种族值** | `MaxHpRace` | int | 生命种族值 |
| | `PhyAttackRace` | int | 物攻种族值 |
| | `MagAttackRace` | int | 魔攻种族值 |
| | `PhyDefenseRace` | int | 物防种族值 |
| | `MagDefenseRace` | int | 魔防种族值 |
| | `SpeedRace` | int | 速度种族值 |
| **天赋值** | `MaxHpTalent` | int | 生命天赋 |
| | `PhyAttackTalent` | int | 物攻天赋 |
| | `MagAttackTalent` | int | 魔攻天赋 |
| | `PhyDefenseTalent` | int | 物防天赋 |
| | `MagDefenseTalent` | int | 魔防天赋 |
| | `SpeedTalent` | int | 速度天赋 |
| **外观** | `PetHeight` | int | 身高 (cm) |
| | `PetWeight` | int | 体重 (g) |
| | `PetCatchBall` | int | 捕捉球 ID (→CDN 图标) |
| | `PetMedal` | string | 奖牌 ID，`/` 分隔 |
| **技能** | `EquipSkill1~4` | int | 装备技能 ID (→SKILL_CONF.json) |
| | `PetBloodline` | int | 血脉 ID |
| **血缘** | `PetBloodline` | int | 血脉 |

### 3. 刷新时间 `/api/pet/getRefreshTime`

**请求方式**: `GET`
**请求参数**: `{}`
**返回**: `{ "next_auto_refresh_time": 1700000000 }` (Unix 时间戳)

### 4. 用户信息 `/api/user/info`

```json
{ "targetUserUin": "", "targetRoleID": "", "settingType": [] }
```

### 5. 静态配置

`https://rocom.qq.com/cp/rocom_game_manager_json/prod/sprite/base_info/{PetBaseId}.json`

单只宠物的静态配置（种族值、系别、进化信息等）。

---

## 二、项目自建后端 API

本项目 FastAPI 后端 (`backend/main.py`) 提供以下接口：

### `GET /api/pets` — 精灵列表（分页）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | 否 | 页码，默认 1 |
| `pageSize` | int | 否 | 每页条数，1~100，默认 20 |
| `name` | string | 否 | 搜索名称 |
| `base_id` | int | 否 | 按种类筛选 |
| `include_inactive` | bool | 否 | 是否包含已放生 |

**返回**: `{ total, page, pageSize, data[] }`

`data[]` 每项包含 `pet_instances.*` 全部字段 + `pet_base_info` 的基础配置 + `pet_natures` 性格信息。

### `GET /api/base_pets` — 可繁育目标种类

返回 `pet_base_info WHERE evolutionStage=1` 的所有精灵种类。

### `GET /api/config/bloodlines` — 血脉映射

**返回**: `{ id: { name, blood_name, blood_type } }`

### `GET /api/config/types` — 系别映射

**返回**: `{ id: { type_name, short_name } }`

### `GET /api/config/medals` — 奖牌映射

**返回**: `{ id: { name, quality, desc } }`

### `POST /api/update_gender` — 设置性别

```json
{ "serial_num": 32088, "gender": 1 }
```
`gender`: 0=未知, 1=雄性, 2=雌性

### `POST /api/recommend_parents` — 繁育推荐

```json
{
  "target_base_id": 3014,
  "desired_nature_id": 2,
  "desired_stats": ["hp", "speed"],
  "use_king_ball": false,
  "king_ball_attr": "hp",
  "breed_big_size": false
}
```

返回 Top 10 父母配对推荐，按综合评分排序。

### `POST /api/sync` — 同步精灵（SSE 事件流）

触发后台线程从游戏服务器拉取数据。通过 `text/event-stream` 实时推送进度。

### `GET /api/sync_status` — 同步冷却状态

```json
{ "cooldown_active": true, "can_sync": false, "remaining_seconds": 3600 }
```

### `GET /api/refresh_time` — 宠物刷新时间

```json
{ "refresh_time": "2026-07-01 16:00:00" }
```

---

## 三、配置映射文件

| 文件 | 路径 | 内容 |
|------|------|------|
| `PET_BLOOD_CONF.json` | `roco_kingdom_world_conf/` | 血脉 ID → 名称 (24条) |
| `TYPE_DICTIONARY.json` | `roco_kingdom_world_conf/` | 系别 ID → 名称 (22条) |
| `MEDAL_CONF.json` | `roco_kingdom_world_conf/` | 奖牌 ID → 名称/品质 (52条) |
| `SKILL_CONF.json` | `roco_kingdom_world_conf/` | 技能 ID → 名称/描述/威力 |
| `PETBASE_CONF.json` | `roco_kingdom_world_conf/` | 精灵基础配置（种族/进化/系别） |
| `PET_EGG_CONF.json` | `roco_kingdom_world_conf/` | 蛋组配置（身高体重范围/孵化时间） |
