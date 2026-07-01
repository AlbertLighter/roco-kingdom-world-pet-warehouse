# 精灵属性字段完整说明

> 对照微信小游戏「精灵详情」页面，说明每个字段的含义、来源和游戏内表现。

---

## 一、基础信息 (顶部)

```
┌───────────────────────────┐
│  [⚪捕捉球]  阿米亚特 ♂   │
│              Lv.1  #32088  │
│  [普通] [🩸普通] [草] [水] │
└───────────────────────────┘
```

### 捕捉球 `catch_ball` (PetCatchBall)
- **含义**: 捕捉该精灵时使用的精灵球类型
- **来源**: `/api/pet/detail` 的 `PetCatchBall` 字段
- **显示**: CDN 图标 `https://game.gtimg.cn/images/rocom/rocodata/Ball/{id}.png`
- **说明**: 不同球种有不同颜色和效果，纯展示用途

### 精灵名称 `name` (PetName)
- **含义**: 精灵名称，原始格式为 `"品种名&自定义名"`
- **来源**: `/api/pet/detail` 的 `PetName`
- **说明**: 前端展示时拆分显示，仅取前半部分

### 序列号 `serial_num` (SerialNum)
- **含义**: 每只精灵的唯一标识，递增的数字
- **来源**: `/api/pet/detail` 的 `SerialNum`
- **说明**: 相当于精灵的「身份证号」

### 等级 `level` (SpiritLevel)
- **含义**: 当前等级
- **来源**: `/api/pet/detail` 的 `SpiritLevel`

### 天赋等级 `talent_rank` (PetTalentRank)
- **含义**: 整体天赋评级
- **值域**: 1=普通, 2=良好, 3=优秀, 4=极品
- **来源**: `/api/pet/list` 和 `/api/pet/detail` 的 `PetTalentRank`
- **判定**: 由精灵个体值总和决定

### 血脉 `bloodline` (PetBloodline)
- **含义**: 精灵的血脉/种族传承
- **映射文件**: `roco_kingdom_world_conf/PET_BLOOD_CONF.json`
- **值域**: 1~24，各系别血脉
- **示例**: 1=普通系血脉, 6=地系血脉, 8=龙系血脉
- **来源**: `/api/pet/detail` 的 `PetBloodline`

### 系别 `skill_dam_type` (PetSkillDamType)
- **含义**: 精灵的属性/系别（可双属性）
- **映射文件**: `roco_kingdom_world_conf/TYPE_DICTIONARY.json`
- **示例**: `[3, 5]` = 草系+水系
- **来源**: `/api/pet/detail` 的 `PetSkillDamType`

### 变异 `mutation` (PetMutation)
- **含义**: 异色/变异形态
- **值域**: 0=无变异, 非0=特定变异类型
- **来源**: `/api/pet/detail` 的 `PetMutation`
- **显示**: 变异精灵在游戏中有不同配色

---

## 二、个体值 (六维面板，雷达图 + 表格)

```
属性    当前    种族    天赋
HP      44      64       0
物攻    64      95       0
物防    46 ↑    67      +9
魔攻    31      47       0
魔防    31      42       0
速度    35 ↓    45      +9
```

### 六维属性对照

| 数据库字段 | API 字段名 | 中文名 | 说明 |
|-----------|-----------|--------|------|
| `hp` | `MaxHp` | 生命 | 决定生存能力 |
| `adAttack` | `PhyAttack` | 物攻 | 物理攻击力 |
| `adDefense` | `PhyDefense` | 物防 | 物理防御力 |
| `apAttack` | `MagAttack` | 魔攻 | 魔法攻击力 |
| `apDefense` | `MagDefense` | 魔防 | 魔法防御力 |
| `speed` | `Speed` | 速度 | 决定行动顺序 |

### 每个属性有三层数值

| 层级 | 数据库字段后缀 | API 字段 | 含义 |
|------|--------------|----------|------|
| **当前值** | `hp` / `adAttack` 等 | `MaxHp` / `PhyAttack` 等 | 面板上显示的最终数值 |
| **种族值** | `hp_race` / `adAttack_race` | `MaxHpRace` / `PhyAttackRace` | 该品种的上限基础，**由母方决定** |
| **天赋值** | `hp_talent` / `adAttack_talent` | `MaxHpTalent` / `PhyAttackTalent` | 额外天赋加点，>0 为优秀属性 |

**当前值公式**: `当前值 = 种族值 + 天赋值`（受等级和性格影响）

### 性格影响 (Nature)

- **性格 ID**: `PetNature` (1~30)
- **数据库**: `pet_natures` 表含 `name`, `plus_stat`, `minus_stat`
- **效果**: 一个属性 +10%，一个属性 -10%
- **显示**: 绿色 ↑ 表示加成，红色 ↓ 表示减益
- **对照表**: 见 `pet_detail_32088.json` 示例

---

## 三、身体数据

### 身高 `height` (PetHeight)
- **单位**: 厘米 (cm)
- **来源**: `/api/pet/detail` 的 `PetHeight`
- **范围**: 每种精灵有 `height_low` ~ `height_high`
- **配置来源**: `roco_kingdom_world_conf/PET_EGG_CONF.json`

### 体重 `weight` (PetWeight)
- **单位**: 克 (g)
- **来源**: `/api/pet/detail` 的 `PetWeight`
- **范围**: 每种精灵有 `weight_low` ~ `weight_high`
- **展示**: 前端转成 kg，带范围标尺

### 蛋组 `egg_group_int` / `egg_groups`
- **含义**: 繁育时相同蛋组才能配对
- **配置来源**: `docs/egg.json`
- **值域**: 1=无法孵蛋, 2=巨灵组, 3=两栖组, ..., 15=机械组
- **映射**: 数字 → 中文名见 `egg_group_mapping` 表

---

## 四、奖牌 (Medal)

```
🏅 大块头, 小不点, 命定勇者
```

- **来源**: `/api/pet/detail` 的 `PetMedal`，格式 `"1001/1003/1028"`
- **映射文件**: `roco_kingdom_world_conf/MEDAL_CONF.json`
- **品质等级**: `quality` 1=普通 ~ 5=传说
- **示例**: 1001=大块头(体型最大), 1002=小不点(体型最小)
- **CDN 图标**: `https://game.gtimg.cn/images/rocom/rocodata/Medal/{id}.png`

---

## 五、技能 (Skills)

### 特性 (Feature)
- **来源**: 根据 `PetBaseId` 从 `PETBASE_CONF.json` 的 `feature` 字段获取特性 ID
- **映射**: `SKILL_CONF.json` 中对应 ID 的 `name`, `desc`
- **特性图标**: `https://game.gtimg.cn/images/rocom/rocodata/jingling/{PetBaseId}/fea.png`

### 装备技能 `equip_skill_1~4`
- **来源**: `/api/pet/detail` 的 `EquipSkill1~4`
- **映射**: `roco_kingdom_world_conf/SKILL_CONF.json`
- **每个技能包含**: 名称、描述、PP值(能量消耗)、威力、系别图标
- **技能图标**: `https://game.gtimg.cn/images/rocom/rocodata/skill/{id}.png`

---

## 六、游戏内截图对照

```
┌──── 顶部 ──────────────────┐
│ 精灵球图标  名称♂  等级     │  ← catch_ball, name, level
├──── 天赋 + 血脉 + 系别 ─────┤
│ [天赋徽章] [血脉名称] [系别] │  ← talent_rank, bloodline, skill_dam_type
├──── 精灵立绘 ──────────────┤
│       🖼 精灵图片            │  ← CDN: jingling/{PetBaseId}/image.png
│      (异色则显示异色版)      │  ← PetMutation 判断
├──── 身体数据 ──────────────┤
│ 体重: 49.00kg  身高: 0.79m  │  ← PetWeight/1000, PetHeight/100
│ 性格: 固执 (+物攻 -魔攻)     │  ← PetNature → natureMap
├──── 个体值 ────────────────┤
│ 生命: 44 (种族64 +天赋0)     │  ← MaxHp + MaxHpRace + MaxHpTalent
│ 物攻: 64 (种族95 +天赋0)     │  ← 带 ↑↓ 性格指示
│ ...                        │
├──── 技能 ──────────────────┤
│ [特性图标] 名称  PP 威力     │  ← Feature + EquipSkill1~4
│ 技能描述...                  │
├──── 奖牌墙 ────────────────┤
│ 🏅 大块头  🏅 小不点         │  ← PetMedal
└────────────────────────────┘
```
