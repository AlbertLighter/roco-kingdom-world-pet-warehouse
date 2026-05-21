# 洛克王国：世界 宠物仓库 API 文档

本文档整理了从抓包数据中分析出的宠物仓库相关 API 接口。

## 基础信息

- **网关地址**: `https://morefun.game.qq.com/gw2/gateway/v1/`
- **请求方式**: `POST`
- **通用参数**: 
  - `X-Mcube-Act-Id`: `E80EH8LJ` (Query String)
  - `authorization`: JWT Token (Header)
  - `data`: 经过 URL 编码的 JSON 字符串 (Body)

---

## 1. 宠物种类汇总列表 (setList)

获取当前仓库中拥有的宠物种类及其数量汇总。

- **请求路径 (`req_path`)**: `/api/pet/setList`
- **请求参数 (`req_param`)**:
  ```json
  {
    "page": 1,
    "pageSize": 40,
    "searchKeyword": "",
    "manual": false,
    "sortOrder": "desc"
  }
  ```
- **返回数据 (`data.list`)**:
  - `PetBaseId` (int): 宠物种类 ID
  - `PetNum` (int): 拥有该种类的宠物总数
  - `PetSkillDamType` (int[]): 宠物属性类型列表（如 [11] 可能代表冰系）

---

## 2. 宠物实例列表 (list)

获取具体的宠物实例列表，可根据种类 ID 过滤。

- **请求路径 (`req_path`)**: `/api/pet/list`
- **请求参数 (`req_param`)**:
  ```json
  {
    "page": 1,
    "pageSize": 40,
    "searchKeyword": "",
    "manual": false,
    "sort": [{"field": "Count", "order": "desc"}],
    "baseid": 3188 // 可选，指定宠物种类 ID
  }
  ```
- **返回数据 (`data.list`)**:
  - `SerialNum` (string): 宠物唯一序列号 (ID)
  - `PetBaseId` (int): 宠物种类 ID
  - `PetTalentRank` (int): 天赋等级 (1-4?)
  - `SpiritLevel` (int): 等级
  - `PetBlood` (int): 血脉等级
  - `PetMutation` (int): 变异值
  - `PetSkillDamType` (int[]): 属性类型

---

## 3. 宠物详细信息 (detail)

获取单个宠物的全量详细属性。

- **请求路径 (`req_path`)**: `/api/pet/detail`
- **请求参数 (`req_param`)**:
  ```json
  {
    "id": "10953" // 宠物的 SerialNum
  }
  ```
- **返回数据 (`data`)**:
  - **基础信息**: `SerialNum`, `PetBaseId`, `PetName`, `SpiritLevel`, `PetNature` (性格ID)
  - **实战能力值**: `MaxHp`, `PhyAttack`, `MagAttack`, `PhyDefense`, `MagDefense`, `Speed`
  - **种族值 (Race)**: `MaxHpRace`, `PhyAttackRace`, `MagAttackRace`, `PhyDefenseRace`, `MagDefenseRace`, `SpeedRace`
  - **天赋值 (Talent)**: `MaxHpTalent`, `PhyAttackTalent`, `MagAttackTalent`, `PhyDefenseTalent`, `MagDefenseTalent`, `SpeedTalent`
  - **其它**: `PetHeight`, `PetWeight`, `PetBloodline`, `EquipSkill1-4` (装备的技能ID), `PetCatchBall` (捕捉球ID)

---

## 4. 宠物种类静态配置 (Base Info)

从静态资源服务器获取宠物的通用基础信息（不包含个体变异、天赋和性格等差异）。

- **URL**: `https://rocom.qq.com/cp/rocom_game_manager_json/prod/sprite/base_info/{PetBaseId}.json`
- **请求方式**: `GET`
- **返回数据 (`JSON` 对象)**:
  - **基础标识**:
    - `id` (int): 内部递增 ID。
    - `objId` (string): 外部宠物种类 ID，等同于 `PetBaseId` (如 "3121")。
    - `name` (string): 宠物名称 (如 "大耳帽兜")。
    - `desc` (string): 宠物的图鉴描述信息。
  - **种族值 (六维属性)**:
    - `hp` (int): 生命种族值。
    - `adAttack` (int): 物理攻击 (PhyAttack) 种族值。
    - `apAttack` (int): 魔法攻击 (MagAttack) 种族值。
    - `adDefense` (int): 物理防御 (PhyDefense) 种族值。
    - `apDefense` (int): 魔法防御 (MagDefense) 种族值。
    - `speed` (int): 速度种族值。
  - **游戏机制属性**:
    - `familyId` (string): 系别/属性 ID（如 "9;16" 为双属性）。
    - `evolutionId` (string): 进化链 ID。
    - `evolutionStage` (int): 当前处于进化链的哪个阶段（例如 1 代表初阶）。
    - `feature` (string): 特性 ID（对应某种被动效果）。
    - `featureDesc` (string): 特性描述（通常为空，可能需要通过另外的接口或配置表获取）。
    - `isSpecial` (int): 是否为特殊宠物 (例如 `1` 表示特殊)。
    - `itemId` (string): 关联道具 ID。
    - `launchType` (string): 投放类型（如 "普通"）。
    - `level` (int): 默认等级/初始等级（通常为 0 或 1）。
    - `shape` (string): 形态说明（为空时表示普通形态）。
  - **系统与发布信息**:
    - `publicAt` (string): 资源预定发布时间（ISO 8601 格式）。
    - `createBy` / `updateBy` (string): 记录的创建者/更新者。
    - `createdAt` / `updatedAt` (string): 记录的创建/更新时间。

---

## 常量与字段说明

### 1. 性格 (PetNature)
在 `detail` 接口中返回的 `PetNature` 为整数 ID。
根据相关逻辑分析，性格会影响属性的加成 (`plus`) 和减益 (`minus`)。已知 ID 示例：
- `13`: (待确认，可能对应某实战性格)
- `15`: (待确认)
- `16`: (待确认)
- `29`: (待确认)

### 2. 系别 (PetSkillDamType / familyId)
对应宠物的属性分类。多个 ID 表示双系别。
已知映射关系（推测）：
- `11`: 冰系 (由“拉特”推测)
- `9, 16`: 冰系 + ? (由“大耳帽兜”推测)
- `20`: ? (由“粉星仔”推测)
- `15`: 火系 (?) (由“里奥”推测)

### 3. 天赋等级 (PetTalentRank)
- `1`: 对应图标颜色/等级（如 蓝色/优秀）
- `2`: (待确认)
- `3`: (待确认)
- `4`: 对应图标颜色/等级（如 橙色/极品）

### 4. 变异与血脉
- `PetMutation`: 变异值，`0` 表示普通，非 `0` 值（如 `32`）代表特定变异。
- `PetBloodline` / `PetBlood`: 血脉等级。

---

## 静态资源关联

可以通过 `PetBaseId` 关联 `docs/egg.json` 中的数据获取宠物的蛋组信息 (`eggGroups`)。例如：
- `PetBaseId: 3121` -> `id: 142` (大耳帽兜) -> `eggGroups: ["妖精组", "拟人组"]`
- `PetBaseId: 3319` -> `id: 259` (粉星仔) -> `eggGroups: ["天空组", "妖精组"]`
- `PetBaseId: 3395` -> `id: 150` (里奥) -> `eggGroups: ["无法孵蛋"]`
