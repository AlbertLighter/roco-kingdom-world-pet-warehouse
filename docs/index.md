# docs 目录索引

> 洛克王国：世界 宠物仓库 — 文档中心

---

## 📖 核心文档

| 文档 | 说明 |
|------|------|
| [`api_documentation.md`](api_documentation.md) | 游戏服务器 API + 项目自建 API 完整参考 |
| [`pet_fields.md`](pet_fields.md) | 精灵属性字段含义详解（对照游戏页面） |
| [`breed_logic.md`](breed_logic.md) | 繁育概率计算器核心算法 |
| [`architecture.md`](architecture.md) | 项目技术架构、数据流、目录结构 |

## 📁 参考数据

| 文件 | 说明 |
|------|------|
| [`egg.json`](egg.json) | 蛋组映射表（宠物ID → 蛋组列表） |
| [`pet_detail_32088.json`](pet_detail_32088.json) | 游戏 API `/api/pet/detail` 响应示例 |

## 🖼 截图

| 文件 | 说明 |
|------|------|
| [`img/warehouse.png`](img/warehouse.png) | 仓库界面截图 |
| [`img/breeding.png`](img/breeding.png) | 繁育中心截图 |

## 🔗 外部资源

- **游戏配置子模块**: `roco_kingdom_world_conf/` (698 个 JSON)
- **游戏 CDN 图片**: `https://game.gtimg.cn/images/rocom/rocodata/`

## ℹ 快速索引

### API 端点速查

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/pets` | GET | 精灵列表（分页搜索） |
| `/api/base_pets` | GET | 可繁育目标种类 |
| `/api/config/bloodlines` | GET | 血脉映射 |
| `/api/config/types` | GET | 系别映射 |
| `/api/config/medals` | GET | 奖牌映射 |
| `/api/update_gender` | POST | 设置精灵性别 |
| `/api/recommend_parents` | POST | 繁育父母推荐 |
| `/api/sync` | POST | 同步精灵数据 (SSE) |
| `/api/sync_status` | GET | 同步冷却状态 |
| `/api/refresh_time` | GET | 游戏刷新时间 |

### 常用命令

```bash
# 启动后端
uv run python backend/main.py

# 同步数据
uv run python scripts/fetcher.py

# 更新子模块
./scripts/sync_conf.sh
```
