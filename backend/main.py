import sqlite3
import json
import itertools
import queue
import threading
import sys
import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List

# Add project root to path so we can import scripts
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- 日志配置 ----
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_sync_logger = logging.getLogger("sync")
_sync_logger.setLevel(logging.INFO)
_handler = logging.FileHandler(os.path.join(_LOG_DIR, "sync.log"), encoding="utf-8", mode="a")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_sync_logger.handlers.clear()
_sync_logger.addHandler(_handler)









_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE_DIR, "..", "warehouse.db")
CONF_DIR = os.path.join(_BASE_DIR, "..", "roco_kingdom_world_conf")

# ---- 加载游戏配置映射（懒加载） ----
_config_cache = {}

def _load_json(filename):
    path = os.path.join(CONF_DIR, filename)
    if not os.path.exists(path):
        return None
    if filename not in _config_cache:
        try:
            with open(path, "r", encoding="utf-8") as f:
                _config_cache[filename] = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            _sync_logger.error(f"配置加载失败 {filename}: {e}")
            return None
    return _config_cache[filename]

def get_bloodline_map():
    data = _load_json("PET_BLOOD_CONF.json")
    if not data:
        return {}
    return {item["id"]: {"name": item["name"], "blood_name": item["blood_name"], "blood_type": item.get("blood_type", 0)} for item in data}

def get_type_map():
    data = _load_json("TYPE_DICTIONARY.json")
    if not data:
        return {}
    return {item["id"]: {"type_name": item["type_name"], "short_name": item["short_name"]} for item in data}

def get_medal_map():
    data = _load_json("MEDAL_CONF.json")
    if not data:
        return {}
    return {item["id"]: {"name": item["name"], "quality": item.get("quality", 1), "desc": item.get("desc", "")} for item in data}

def get_talent_skill_map():
    """特长映射 (PET_TALENT_CONF) ID → { name, desc }"""
    data = _load_json("PET_TALENT_CONF.json")
    if not data:
        return {}
    return {item["id"]: {"name": item["name"], "desc": item.get("desc", "")} for item in data}

def get_nature_map():
    """性格映射，包含 buff/debuff 对应的属性下标 (0-5 对应 hp/adAttack/adDefense/apAttack/apDefense/speed)"""
    data = _load_json("PET_BLOOD_CONF.json")
    if not data:
        return {}
    # PETBASE_CONF 的 nature_ids 字段，但这里直接从数据库获取
    return {}


def init_db():
    """启动时自动创建数据库表（如不存在）"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # pet_base_info: 宠物基础信息
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pet_base_info (
        id INTEGER PRIMARY KEY,
        name TEXT,
        description TEXT,
        hp INTEGER,
        adAttack INTEGER,
        apAttack INTEGER,
        adDefense INTEGER,
        apDefense INTEGER,
        speed INTEGER,
        familyId TEXT,
        itemId INTEGER,
        objId INTEGER,
        evolutionStage INTEGER,
        evolutionId TEXT,
        egg_groups TEXT,
        egg_group_int TEXT,
        height_high INTEGER,
        height_low INTEGER,
        weight_high INTEGER,
        weight_low INTEGER
    )
    """)

    # pet_instances: 玩家拥有的宠物实例
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pet_instances (
        serial_num INTEGER PRIMARY KEY,
        base_id INTEGER,
        name TEXT,
        level INTEGER,
        nature INTEGER,
        talent_rank INTEGER,
        hp INTEGER,
        adAttack INTEGER,
        apAttack INTEGER,
        adDefense INTEGER,
        apDefense INTEGER,
        speed INTEGER,
        hp_race INTEGER,
        adAttack_race INTEGER,
        apAttack_race INTEGER,
        adDefense_race INTEGER,
        apDefense_race INTEGER,
        speed_race INTEGER,
        hp_talent INTEGER,
        adAttack_talent INTEGER,
        apAttack_talent INTEGER,
        adDefense_talent INTEGER,
        apDefense_talent INTEGER,
        speed_talent INTEGER,
        is_active INTEGER DEFAULT 1,
        gender INTEGER DEFAULT 0,
        medal TEXT,
        catch_ball INTEGER,
        height INTEGER,
        weight INTEGER,
        bloodline INTEGER DEFAULT 0,
        skill_dam_type TEXT,
        equip_skill_1 INTEGER DEFAULT 0,
        equip_skill_2 INTEGER DEFAULT 0,
        equip_skill_3 INTEGER DEFAULT 0,
        equip_skill_4 INTEGER DEFAULT 0,
        mutation INTEGER DEFAULT 0,
        talent_skill INTEGER DEFAULT 0,
        FOREIGN KEY (base_id) REFERENCES pet_base_info (id)
    )
    """)

    # pet_natures: 性格数据
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pet_natures (
        id INTEGER PRIMARY KEY,
        name TEXT,
        plus_stat TEXT,
        minus_stat TEXT
    )
    """)
    natures = [
        (1, "大胆", "物攻", "物防"), (2, "固执", "物攻", "魔攻"), (3, "调皮", "物攻", "魔抗"),
        (4, "勇敢", "物攻", "速度"), (5, "逞强", "物攻", "生命"), (6, "稳重", "物防", "物攻"),
        (7, "天真", "物防", "魔攻"), (8, "懒散", "物防", "魔防"), (9, "悠闲", "物防", "速度"),
        (10, "坦率", "物防", "生命"), (11, "聪明", "魔攻", "物攻"), (12, "专注", "魔攻", "物防"),
        (13, "偏执", "魔攻", "魔防"), (14, "冷静", "魔攻", "速度"), (15, "理性", "魔攻", "生命"),
        (16, "警惕", "魔防", "物攻"), (17, "温顺", "魔抗", "物防"), (18, "害羞", "魔防", "魔攻"),
        (19, "慎重", "魔抗", "速度"), (20, "焦虑", "魔防", "生命"), (21, "胆小", "速度", "物攻"),
        (22, "急躁", "速度", "物防"), (23, "开朗", "速度", "魔攻"), (24, "莽撞", "速度", "魔防"),
        (25, "热情", "速度", "生命"), (26, "沉默", "生命", "物攻"), (27, "忧郁", "生命", "物防"),
        (28, "平和", "生命", "魔攻"), (29, "粗心", "生命", "魔防"), (30, "踏实", "生命", "速度")
    ]
    cursor.executemany("INSERT OR REPLACE INTO pet_natures (id, name, plus_stat, minus_stat) VALUES (?, ?, ?, ?)", natures)

    # settings: 键值存储
    # ---- 向后兼容迁移：旧数据库缺少的列 ----
    _migrate_cols = [
        ("pet_instances", "bloodline", "INTEGER DEFAULT 0"),
        ("pet_instances", "skill_dam_type", "TEXT"),
        ("pet_instances", "equip_skill_1", "INTEGER DEFAULT 0"),
        ("pet_instances", "equip_skill_2", "INTEGER DEFAULT 0"),
        ("pet_instances", "equip_skill_3", "INTEGER DEFAULT 0"),
        ("pet_instances", "equip_skill_4", "INTEGER DEFAULT 0"),
        ("pet_instances", "mutation", "INTEGER DEFAULT 0"),
        ("pet_instances", "talent_skill", "INTEGER DEFAULT 0"),
        ("breeding_slots", "nature_id", "INTEGER"),
        ("breeding_slots", "talents", "TEXT"),
        ("breeding_slots", "use_king_ball", "INTEGER DEFAULT 0"),
        ("breeding_slots", "king_ball_attr", "TEXT"),
        ("breeding_slots", "breed_big_size", "INTEGER DEFAULT 0"),
    ]
    for table, col, typedef in _migrate_cols:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            print(f"迁移: {table}.{col} 已添加")
        except sqlite3.OperationalError:
            pass

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # egg_group_mapping: 蛋组映射
    # breeding_slots: 家园繁育槽位（5组×父/母/目标）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS breeding_slots (
        slot_id INTEGER PRIMARY KEY CHECK(slot_id BETWEEN 1 AND 5),
        target_base_id INTEGER,
        father_serial INTEGER,
        mother_serial INTEGER,
        updated_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (father_serial) REFERENCES pet_instances(serial_num),
        FOREIGN KEY (mother_serial) REFERENCES pet_instances(serial_num)
    )
    """)
    # 确保5个默认槽位存在
    for i in range(1, 6):
        cursor.execute("INSERT OR IGNORE INTO breeding_slots (slot_id) VALUES (?)", (i,))

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS egg_group_mapping (
        group_id INTEGER PRIMARY KEY,
        group_name TEXT NOT NULL
    )
    """)
    egg_group_mapping = [
        (1, "无法孵蛋"), (2, "巨灵组"), (3, "两栖组"), (4, "昆虫组"),
        (5, "天空组"), (6, "动物组"), (7, "妖精组"), (8, "植物组"),
        (9, "拟人组"), (10, "软体组"), (11, "大地组"), (12, "魔力组"),
        (13, "海洋组"), (14, "龙组"), (15, "机械组"),
    ]
    cursor.executemany("INSERT OR REPLACE INTO egg_group_mapping (group_id, group_name) VALUES (?, ?)", egg_group_mapping)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS species_preferences (
        base_id INTEGER PRIMARY KEY,
        preferred_nature_id INTEGER DEFAULT 0,
        keep_count INTEGER DEFAULT 3,
        updated_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (base_id) REFERENCES pet_base_info(id)
    )
    """)

    # ---- 向后兼容迁移：preferred_nature_ids ----
    cursor.execute("PRAGMA table_info(species_preferences)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "preferred_nature_ids" not in existing_cols:
        cursor.execute("ALTER TABLE species_preferences ADD COLUMN preferred_nature_ids TEXT DEFAULT '[]'")
        cursor.execute("""
            UPDATE species_preferences
            SET preferred_nature_ids = CASE WHEN preferred_nature_id > 0
                THEN '[' || preferred_nature_id || ']' ELSE '[]' END
        """)

    conn.commit()
    conn.close()
    print("数据库已初始化（表已就绪）")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库"""
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

# Global lock to prevent concurrent sync runs
_sync_lock = threading.Lock()
_gender_sync_lock = threading.Lock()

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 全局异常日志中间件 ----
@app.middleware("http")
async def log_unhandled_errors(request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        _sync_logger.error(f"未处理的请求异常: {request.method} {request.url.path} - {e}")
        raise

class BreedCalculator:
    def __init__(self, father_attrs, mother_attrs, king_ball_attr=None):
        """
        father_attrs: list of strings (e.g., ["hp", "speed"])
        mother_attrs: list of strings
        king_ball_attr: optional string
        """
        self.slots = ["hp", "adAttack", "adDefense", "apAttack", "apDefense", "speed"]
        self.father_set = set(father_attrs)
        self.mother_set = set(mother_attrs)
        self.father_num = len(self.father_set)
        self.mother_num = len(self.mother_set)
        self.king_ball_attr = king_ball_attr
        self.is_king_ball = king_ball_attr is not None
        
        self.weights = {}
        for s in self.slots:
            cnt = (1 if s in self.father_set else 0) + (1 if s in self.mother_set else 0)
            self.weights[s] = 100 + 300 * cnt
            
        self.total_weight = sum(self.weights.values())
        
        if self.is_king_ball:
            self.effective_slots = [s for s in self.slots if s != self.king_ball_attr]
            self.effective_weights = {s: self.weights[s] for s in self.effective_slots}
            self.total_effective_weight = sum(self.effective_weights.values())
            self.effective_k = 2
            self.prob1 = self.prob2 = 0
            self.prob3 = 1.0
        else:
            self._calc_count_probs()
            
    def _calc_count_probs(self):
        w1 = 0
        w2 = 100 + (300 if self.father_num == 2 else 0) + (300 if self.mother_num == 2 else 0)
        w3 = 100 + (300 if self.father_num == 3 else 0) + (300 if self.mother_num == 3 else 0)
        total = w1 + w2 + w3
        if total == 0:
            self.prob1 = self.prob2 = self.prob3 = 0
        else:
            self.prob1 = w1 / total
            self.prob2 = w2 / total
            self.prob3 = w3 / total

    def probability_of_exact_combo(self, combo):
        # combo is a tuple/list of strings
        prob = 0
        for perm in itertools.permutations(combo):
            p = 1.0
            remaining_w = self.total_weight
            for s in perm:
                p *= self.weights[s] / remaining_w
                remaining_w -= self.weights[s]
            prob += p
        return prob

    def probability_of_effective_combo(self, combo):
        # combo should be length 2
        prob = 0
        for perm in itertools.permutations(combo):
            p = 1.0
            remaining_w = self.total_effective_weight
            for s in perm:
                p *= self.effective_weights[s] / remaining_w
                remaining_w -= self.effective_weights[s]
            prob += p
        return prob

    def get_target_prob(self, target_attrs):
        target_set = set(target_attrs)
        if not target_set:
            return 1.0
        
        if self.is_king_ball:
            if self.king_ball_attr not in target_set:
                return 0
            
            remaining_target = [s for s in target_set if s != self.king_ball_attr]
            if len(remaining_target) > 2:
                return 0
            if not remaining_target:
                return 1.0
            
            total_prob = 0
            for combo in itertools.combinations(self.effective_slots, 2):
                if all(t in combo for t in remaining_target):
                    total_prob += self.probability_of_effective_combo(combo)
            return total_prob
        else:
            total_prob = 0
            for k, prob_k in [(2, self.prob2), (3, self.prob3)]:
                if prob_k <= 0: continue
                sum_k = 0
                for combo in itertools.combinations(self.slots, k):
                    if target_set.issubset(set(combo)):
                        sum_k += self.probability_of_exact_combo(combo)
                total_prob += prob_k * sum_k
            return total_prob

def _build_pet_filter(name, base_id, include_inactive):
    """Build WHERE clause and params for pet queries. All user values go through ? placeholders."""
    where_parts = []
    params = []

    if not include_inactive:
        where_parts.append("i.is_active = 1")
    if name:
        where_parts.append("(i.name LIKE ? OR b.name LIKE ?)")
        params.extend([f"%{name}%", f"%{name}%"])
    if base_id is not None:
        where_parts.append("i.base_id = ?")
        params.append(base_id)

    where_str = " AND ".join(where_parts) if where_parts else "1=1"
    return where_str, params


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/config/bloodlines")
def get_bloodlines():
    """获取血脉配置映射"""
    return get_bloodline_map()

@app.get("/api/config/types")
def get_types():
    """获取系别配置映射"""
    return get_type_map()

@app.get("/api/config/medals")
def get_medals():
    """获取奖牌配置映射"""
    return get_medal_map()

@app.get("/api/config/talent_skills")
def get_talent_skills():
    """获取特长配置映射"""
    return get_talent_skill_map()

@app.get("/api/pets")
def get_pets(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    name: Optional[str] = None,
    base_id: Optional[int] = None,
    include_inactive: bool = Query(False)
):
    conn = get_db_connection()
    cursor = conn.cursor()

    where_str, params = _build_pet_filter(name, base_id, include_inactive)
    
    # 1. 获取总数
    count_query = f"""
    SELECT COUNT(*) FROM (
        SELECT i.serial_num
        FROM pet_instances i
        JOIN pet_base_info b ON i.base_id = b.objId
        WHERE {where_str}
    ) AS t
    """
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]
    
    # 2. 获取分页详细数据
    data_query = f"""
    SELECT 
        i.*, 
        b.name as base_name, 
        b.description as base_description,
        b.familyId as base_familyId,
        b.itemId as base_itemId,
        b.egg_groups as base_egg_groups,
        b.egg_group_int as base_egg_group_int,
        b.height_high as base_height_high,
        b.height_low as base_height_low,
        b.weight_high as base_weight_high,
        b.weight_low as base_weight_low,
        n.name as nature_name,
        n.plus_stat as nature_plus,
        n.minus_stat as nature_minus
    FROM pet_instances i
    JOIN pet_base_info b ON i.base_id = b.objId
    LEFT JOIN pet_natures n ON i.nature = n.id
    WHERE {where_str}
    ORDER BY i.serial_num DESC
    LIMIT ? OFFSET ?
    """
    
    data_params = params + [pageSize, (page - 1) * pageSize]
    
    cursor.execute(data_query, data_params)
    rows = cursor.fetchall()
    
    pets = [dict(row) for row in rows]
    conn.close()
    
    return {
        "total": total,
        "page": page,
        "pageSize": pageSize,
        "data": pets
    }

@app.get("/api/base_pets")
def get_base_pets():
    """获取可以作为繁育目标的精灵种类 (evolutionStage=1)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pet_base_info WHERE evolutionStage = 1 ORDER BY name")
    rows = cursor.fetchall()
    res = [dict(row) for row in rows]
    conn.close()
    return res

@app.post("/api/update_gender")
def update_gender(serial_num: int = Body(...), gender: int = Body(...)):
    """更新精灵性别 (0:未知, 1:雄性, 2:雌性)"""
    if gender not in [0, 1, 2]:
        raise HTTPException(status_code=400, detail="Invalid gender value")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE pet_instances SET gender = ? WHERE serial_num = ?", (gender, serial_num))
    conn.commit()
    conn.close()
    return {"msg": "Gender updated"}


@app.post("/api/sync_gender_export")
def sync_gender_from_export_endpoint():
    """从 data/ 目录的抓包导出文件同步精灵性别，通过 SSE 流式返回进度。"""
    if not _gender_sync_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="性别同步任务正在运行中")

    def event_stream():
        import queue as _queue

        progress_queue = _queue.Queue()

        def progress_callback(message, current=0, total=0):
            progress_queue.put({
                "message": message,
                "current": current,
                "total": total
            })

        def run_task():
            try:
                from scripts.sync_gender_from_export import sync_gender_from_export
                result = sync_gender_from_export(progress_callback=progress_callback)
                progress_queue.put({"done": True, "result": result})
                _sync_logger.info(f"性别同步完成：更新 {result.get('updated', 0)} 条，匹配 {result.get('matched', 0)} 条")
            except Exception as e:
                _sync_logger.error(f"性别同步失败: {e}")
                progress_queue.put({"done": True, "error": str(e)})
            finally:
                _gender_sync_lock.release()

        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()

        while True:
            try:
                msg = progress_queue.get(timeout=60)
            except _queue.Empty:
                yield f"data: {json.dumps({'message': '心跳...', 'current': 0, 'total': 0})}\n\n"
                continue

            if msg.get("done"):
                if msg.get("error"):
                    yield f"data: {json.dumps({'error': msg['error']})}\n\n"
                else:
                    yield f"data: {json.dumps({'done': True, 'result': msg.get('result', {})})}\n\n"
                break
            else:
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


_STAT_COLS = {
    "hp": "hp_talent",
    "adAttack": "adAttack_talent",
    "apAttack": "apAttack_talent",
    "adDefense": "adDefense_talent",
    "apDefense": "apDefense_talent",
    "speed": "speed_talent"
}

# ---- 放生推荐评分引擎常量 ----
TALENT_SKILL_RIDE = 402          # 同乘
TALENT_SKILL_SHARE = 1001        # 爱分享
TALENT_SKILL_MERCY = 50001       # 慈悲为怀
MUTATION_KEEP = {1, 8, 9}        # 异色/炫彩/异色炫彩，无条件保留
SPEED_NATURES = {21, 22, 23, 24, 25}  # 加速度的性格 ID（来自 NATURE_CONF）


def compute_pet_score(pet: dict, preferred_nature_ids: list = None) -> float:
    """
    计算精灵个体价值评分 (0~100)，分数越低越建议放生。

    评分维度：
      - 天赋分 (0~40): 六项天赋值总和 / 186 * 40
      - 天赋等级分 (0~15): 普通=0, 良好=5, 优秀=10, 极品=15
      - 体型分 (0~15): 身高体重在该品种范围内的百分位均值 * 15
      - 性格分 (0~15): 匹配任一偏好=15, 未指定=7.5, 不匹配=5
      - 特长加分 (0~15): 有特长=10, 慈悲为怀=15, 无=0
    """
    if preferred_nature_ids is None:
        preferred_nature_ids = []
    # 1. 天赋分 (0~40)
    total_talent = sum(pet.get(f"{s}_talent", 0) for s in _STAT_COLS)
    talent_score = min(40, total_talent / 186 * 40)

    # 2. 天赋等级分 (0~15)
    rank_map = {1: 0, 2: 5, 3: 10, 4: 15}
    rank_score = rank_map.get(pet.get("talent_rank", 1), 0)

    # 3. 体型分 (0~15): 复用 _get_size_score 的百分位逻辑
    size_pct = _get_size_score(pet)
    size_score = size_pct * 15

    # 4. 性格分 (0~15): 匹配任一偏好性格即得满分
    nature_id = pet.get("nature", 0)
    if not preferred_nature_ids:
        nature_score = 7.5
    elif nature_id in preferred_nature_ids:
        nature_score = 15
    else:
        nature_score = 5

    # 5. 特长加分 (0~15)
    talent_skill = pet.get("talent_skill", 0)
    if talent_skill == TALENT_SKILL_MERCY:
        skill_bonus = 15
    elif talent_skill in (TALENT_SKILL_RIDE, TALENT_SKILL_SHARE):
        skill_bonus = 10
    else:
        skill_bonus = 0

    score = talent_score + rank_score + size_score + nature_score + skill_bonus
    return round(min(100, score), 1)


def rank_ride_pets(ride_pets: list) -> list:
    """
    对同乘精灵按保留优先级排序（降序）。

    排序依据：
      1. speed_talent 天赋值 (×3 权重)
      2. 是否加速度性格 (加分 10)
      3. talent_rank 等级 (×2 权重)
      4. 体型微小加成
    """
    for p in ride_pets:
        speed_t = p.get("speed_talent", 0)
        nature_bonus = 10 if p.get("nature", 0) in SPEED_NATURES else 0
        rank_bonus = {1: 0, 2: 2, 3: 4, 4: 6}.get(p.get("talent_rank", 1), 0)
        size = (p.get("height", 0) or 0) + (p.get("weight", 0) or 0) / 1000
        p["_ride_score"] = speed_t * 3 + nature_bonus + rank_bonus + size / 10000
    return sorted(ride_pets, key=lambda p: p["_ride_score"], reverse=True)


def compute_species_recommendations(
    all_pets: list,
    base_info: dict,
    preferred_nature_ids: list = None,
    keep_count: int = 3
) -> dict:
    """
    对一个品种内的所有精灵计算放生推荐。

    决策顺序：
      1. mutation IN (1,8,9) → 无条件保留
      2. 慈悲为怀 → 全部保留
      3. 同乘 → 选最优 1 只保留
      4. 爱分享 → 选最优 1 只保留
      5. 母方体型最优 → 各家族保留体型最大的母方 1 只
      6. 普通精灵按评分排序，保留前 keep_count 只
      7. 其余标记为建议放生

    返回: {
        "total_count": int,
        "keep_count": int,
        "recommended_count": int,
        "kept_serials": [int, ...],
        "recommended_serials": [int, ...],
        "pets": [{serial_num, score, is_recommended, is_kept, reasons}, ...]
    }
    """
    if not all_pets:
        return {
            "total_count": 0, "keep_count": 0, "recommended_count": 0,
            "kept_serials": [], "recommended_serials": [], "pets": []
        }

    kept_serials = set()

    # --- 步骤 1: mutation 无条件保留 ---
    mutation_keep = [p for p in all_pets if p.get("mutation", 0) in MUTATION_KEEP]
    for p in mutation_keep:
        kept_serials.add(p["serial_num"])

    # --- 步骤 2: 慈悲为怀全部保留 ---
    mercy_pets = [p for p in all_pets if p.get("talent_skill", 0) == TALENT_SKILL_MERCY]
    for p in mercy_pets:
        kept_serials.add(p["serial_num"])

    # --- 步骤 3: 同乘优选 ---
    ride_pets = [
        p for p in all_pets
        if p.get("talent_skill", 0) == TALENT_SKILL_RIDE
        and p["serial_num"] not in kept_serials
    ]
    if ride_pets:
        ranked_rides = rank_ride_pets(ride_pets)
        kept_serials.add(ranked_rides[0]["serial_num"])

    # --- 步骤 4: 爱分享优选 ---
    share_pets = [
        p for p in all_pets
        if p.get("talent_skill", 0) == TALENT_SKILL_SHARE
        and p["serial_num"] not in kept_serials
    ]
    if share_pets:
        ranked_shares = sorted(
            share_pets,
            key=lambda p: sum(p.get(f"{s}_talent", 0) for s in _STAT_COLS),
            reverse=True
        )
        kept_serials.add(ranked_shares[0]["serial_num"])

    # --- 步骤 5: 母方体型最优保留（用于繁育）---
    female_pets = [
        p for p in all_pets
        if p.get("gender", 0) == 2
        and p["serial_num"] not in kept_serials
    ]
    if female_pets:
        # 按体型大小（身高+体重）降序，取最大的保留
        female_pets.sort(key=lambda p: (p.get("height", 0) or 0) + (p.get("weight", 0) or 0), reverse=True)
        kept_serials.add(female_pets[0]["serial_num"])

    # --- 步骤 6: 常规评分排序 ---
    normal_pets = [p for p in all_pets if p["serial_num"] not in kept_serials]
    scored_pets = []
    for p in normal_pets:
        score = compute_pet_score(p, preferred_nature_ids)
        reasons = _compute_release_reasons(p, preferred_nature_ids, all_pets)
        scored_pets.append({
            "serial_num": p["serial_num"],
            "score": score,
            "reasons": reasons,
        })
    scored_pets.sort(key=lambda x: x["score"], reverse=True)

    # 保留评分最高的 keep_count 只
    for sp in scored_pets[:keep_count]:
        kept_serials.add(sp["serial_num"])

    # --- 步骤 7: 确定推荐放生集 ---
    result_pets = []
    recommended_serials = []
    for p in all_pets:
        sn = p["serial_num"]
        if sn in kept_serials:
            result_pets.append({
                "serial_num": sn,
                "score": next(
                    (sp["score"] for sp in scored_pets if sp["serial_num"] == sn),
                    compute_pet_score(p, preferred_nature_ids)
                ),
                "is_recommended": False,
                "is_kept": True,
                "reasons": [],
            })
        else:
            reasons = next(
                (sp["reasons"] for sp in scored_pets if sp["serial_num"] == sn),
                ["综合评分较低"]
            )
            result_pets.append({
                "serial_num": sn,
                "score": next(
                    (sp["score"] for sp in scored_pets if sp["serial_num"] == sn),
                    compute_pet_score(p, preferred_nature_ids)
                ),
                "is_recommended": True,
                "is_kept": False,
                "reasons": reasons,
            })
            recommended_serials.append(sn)

    return {
        "total_count": len(all_pets),
        "keep_count": len(kept_serials),
        "recommended_count": len(recommended_serials),
        "kept_serials": sorted(kept_serials),
        "recommended_serials": sorted(recommended_serials),
        "pets": result_pets,
    }


_RELEASE_REASON_TEMPLATES = {
    "mutation_keep": "异色/炫彩变异",
    "mercy_keep": "特长：慈悲为怀",
    "ride_kept_best": "同乘优选保留",
    "ride_has_better": "同乘特长，但有更好的同乘个体",
    "share_kept_best": "爱分享优选保留",
    "share_has_better": "爱分享特长，但有更好的爱分享个体",
    "no_talent_low": "无特长，天赋总和较低",
    "beyond_quota": "已超出该品种最少保留数量",
    "low_score": "综合评分较低",
}


def _compute_release_reasons(pet: dict, preferred_nature_ids: list, species_pets: list) -> list:
    """计算一只精灵被推荐放生的理由文案。"""
    reasons = []
    talent_skill = pet.get("talent_skill", 0)

    if talent_skill == TALENT_SKILL_RIDE:
        reasons.append(_RELEASE_REASON_TEMPLATES["ride_has_better"])
    elif talent_skill == TALENT_SKILL_SHARE:
        reasons.append(_RELEASE_REASON_TEMPLATES["share_has_better"])
    elif talent_skill == 0:
        total_t = sum(pet.get(f"{s}_talent", 0) for s in _STAT_COLS)
        if total_t < 50:
            reasons.append(_RELEASE_REASON_TEMPLATES["no_talent_low"])

    if preferred_nature_ids and pet.get("nature", 0) not in preferred_nature_ids:
        reasons.append("性格与该品种偏好不匹配")

    if not reasons:
        reasons.append(_RELEASE_REASON_TEMPLATES["beyond_quota"])

    return reasons


_KNOWN_TALENT_SKILL_NAMES = None


def _get_talent_skill_name(talent_skill_id: int) -> str:
    """根据特长 ID 获取中文名称（懒加载配置映射）。"""
    global _KNOWN_TALENT_SKILL_NAMES
    if _KNOWN_TALENT_SKILL_NAMES is None:
        raw = get_talent_skill_map()
        _KNOWN_TALENT_SKILL_NAMES = {k: v["name"] for k, v in raw.items()}
    return _KNOWN_TALENT_SKILL_NAMES.get(talent_skill_id, "")


def _get_size_score(pet: dict) -> float:
    """Calculate body size score (0~1) for big-size breeding preference."""
    h = pet.get("height") or 0
    hl = pet.get("base_height_low") or 0
    hh = pet.get("base_height_high") or 1
    w = pet.get("weight") or 0
    wl = pet.get("base_weight_low") or 0
    wh = pet.get("base_weight_high") or 1
    hs = (h - hl) / (hh - hl) if hh > hl else 0
    ws = (w - wl) / (wh - wl) if wh > wl else 0
    return max(0, min(1, (hs + ws) / 2))


def _get_excellent_stats(pet: dict) -> list:
    """Return stat keys where the pet has a positive talent (top 3)."""
    return [k for k, col in _STAT_COLS.items() if pet.get(col, 0) > 0][:3]


def _calc_nature_prob(mother: dict, father: dict, desired_nature_id: int, natures_count: int) -> float:
    """Calculate nature inheritance probability."""
    p = 0
    if father["nature"] == desired_nature_id:
        p += 0.35
    if mother["nature"] == desired_nature_id:
        p += 0.35
    p += 0.3 * (1.0 / natures_count)
    return p


def _build_pair(mother: dict, father: dict, total_prob: float, size_score: float) -> dict:
    """Build recommendation dict for a mother-father pair."""
    mother_full = dict(mother)
    mother_full["name"] = mother["base_name"]
    father_full = dict(father)
    father_full["name"] = father["base_name"]
    score = round(total_prob * 100 + size_score * 50, 2)
    return {
        "mother": mother_full,
        "father": father_full,
        "probability": total_prob,
        "size_score": round(size_score * 100, 2),
        "score": score
    }


@app.post("/api/recommend_parents")
def recommend_parents(
    target_base_id: int = Body(...),
    desired_nature_id: Optional[int] = Body(None),
    desired_stats: List[str] = Body([]),
    use_king_ball: bool = Body(False),
    king_ball_attr: Optional[str] = Body(None),
    breed_big_size: bool = Body(False)
):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pet_natures")
    natures_count = cursor.fetchone()[0] or 30

    # 1. 校验目标精灵
    cursor.execute("SELECT * FROM pet_base_info WHERE objId = ?", (target_base_id,))
    target = cursor.fetchone()
    if not target or target["evolutionStage"] != 1:
        raise HTTPException(status_code=400, detail="Target must be base form (stage 1)")

    target_evo_ids = set(json.loads(target["evolutionId"]) if target["evolutionId"] else [])

    # 2. 查询所有合格母方（进化链包含目标精灵）
    cursor.execute("""
        SELECT i.*, b.familyId, b.egg_groups, b.evolutionId, b.name as base_name,
               b.height_low as base_height_low, b.height_high as base_height_high,
               b.weight_low as base_weight_low, b.weight_high as base_weight_high,
               n.name as nature_name, n.plus_stat as nature_plus, n.minus_stat as nature_minus
        FROM pet_instances i
        JOIN pet_base_info b ON i.base_id = b.objId
        LEFT JOIN pet_natures n ON i.nature = n.id
        WHERE i.is_active = 1 AND i.gender != 1
    """)
    qualified_mothers = []
    for row in cursor.fetchall():
        d = dict(row)
        evo_ids = set(json.loads(d["evolutionId"]) if d["evolutionId"] else [])
        if evo_ids.issubset(target_evo_ids):
            qualified_mothers.append(d)

    # 3. 查询所有合格父方
    cursor.execute("""
        SELECT i.*, b.familyId, b.egg_groups, b.name as base_name,
               b.height_low as base_height_low, b.height_high as base_height_high,
               b.weight_low as base_weight_low, b.weight_high as base_weight_high,
               n.name as nature_name, n.plus_stat as nature_plus, n.minus_stat as nature_minus
        FROM pet_instances i
        JOIN pet_base_info b ON i.base_id = b.objId
        LEFT JOIN pet_natures n ON i.nature = n.id
        WHERE i.is_active = 1 AND i.gender != 2
    """)
    all_males = [dict(row) for row in cursor.fetchall()]

    # 4. 配对打分
    recommendations = []
    for mother in qualified_mothers:
        m_eggs = set(json.loads(mother["egg_groups"]) if mother["egg_groups"] else [])
        m_excellent = _get_excellent_stats(mother)

        for father in all_males:
            f_eggs = set(json.loads(father["egg_groups"]) if father["egg_groups"] else [])
            if not m_eggs.intersection(f_eggs):
                continue

            f_excellent = _get_excellent_stats(father)

            calc = BreedCalculator(f_excellent, m_excellent, king_ball_attr if use_king_ball else None)
            attr_prob = calc.get_target_prob(desired_stats)

            nature_prob = 1.0
            if desired_nature_id:
                nature_prob = _calc_nature_prob(mother, father, desired_nature_id, natures_count)

            total_prob = attr_prob * nature_prob

            size_score = 0
            if breed_big_size:
                size_score = (_get_size_score(mother) + _get_size_score(father)) / 2

            recommendations.append(_build_pair(mother, father, total_prob, size_score))

    recommendations.sort(key=lambda x: x["score"], reverse=True)
    conn.close()
    return recommendations[:10]


# ---- 家园生蛋配置（5组配对） ----
def _get_pet_minimal(pet_row: dict) -> dict:
    """Extract a minimal pet summary from a raw DB row."""
    return {
        "serial_num": pet_row["serial_num"],
        "name": pet_row["base_name"] or pet_row["name"],
        "level": pet_row["level"],
        "gender": pet_row["gender"],
        "talent_rank": pet_row["talent_rank"],
        "nature_name": pet_row.get("nature_name"),
    }


@app.get("/api/breeding_slots")
def get_breeding_slots():
    """获取全部5个繁育槽位配置（含宠物详情）"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            s.slot_id, s.target_base_id, s.father_serial, s.mother_serial,
            s.nature_id, s.talents, s.use_king_ball, s.king_ball_attr, s.breed_big_size,
            s.updated_at,
            b.name as target_name,
            f.serial_num as f_serial, f.name as f_name, f.level as f_level,
            f.gender as f_gender, f.talent_rank as f_talent_rank,
            fn.name as f_nature_name,
            m.serial_num as m_serial, m.name as m_name, m.level as m_level,
            m.gender as m_gender, m.talent_rank as m_talent_rank,
            mn.name as m_nature_name
        FROM breeding_slots s
        LEFT JOIN pet_base_info b ON s.target_base_id = b.objId
        LEFT JOIN pet_instances f ON s.father_serial = f.serial_num
        LEFT JOIN pet_natures fn ON f.nature = fn.id
        LEFT JOIN pet_instances m ON s.mother_serial = m.serial_num
        LEFT JOIN pet_natures mn ON m.nature = mn.id
        ORDER BY s.slot_id
    """)
    rows = cursor.fetchall()
    conn.close()

    slots = []
    for row in rows:
        d = dict(row)
        slot = {
            "slot_id": d["slot_id"],
            "target_base_id": d["target_base_id"],
            "target_name": d["target_name"],
            "father": None,
            "mother": None,
            "nature_id": d["nature_id"],
            "talents": d["talents"],
            "use_king_ball": d["use_king_ball"],
            "king_ball_attr": d["king_ball_attr"],
            "breed_big_size": d["breed_big_size"],
            "updated_at": d["updated_at"],
        }
        if d["f_serial"]:
            slot["father"] = {
                "serial_num": d["f_serial"], "name": d["f_name"],
                "level": d["f_level"], "gender": d["f_gender"],
                "talent_rank": d["f_talent_rank"], "nature_name": d["f_nature_name"],
            }
        if d["m_serial"]:
            slot["mother"] = {
                "serial_num": d["m_serial"], "name": d["m_name"],
                "level": d["m_level"], "gender": d["m_gender"],
                "talent_rank": d["m_talent_rank"], "nature_name": d["m_nature_name"],
            }
        slots.append(slot)
    return slots


@app.put("/api/breeding_slots")
def update_breeding_slots(slots: List[dict] = Body(...)):
    """批量更新繁育槽位（5组）。Body: [{slot_id, target_base_id, father_serial, mother_serial}]"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 收集所有被占用的 serial_num 去重检查
    used = set()
    for s in slots:
        sid = s.get("slot_id")
        if not sid or not (1 <= sid <= 5):
            continue
        father = s.get("father_serial")
        mother = s.get("mother_serial")
        for p in [father, mother]:
            if p is not None:
                p_int = int(p)
                if p_int in used:
                    conn.close()
                    raise HTTPException(status_code=400, detail=f"精灵 {p_int} 在多个槽位中重复，每个精灵只能出现一次")
                used.add(p_int)

    for s in slots:
        sid = s.get("slot_id")
        if not sid or not (1 <= sid <= 5):
            continue
        target = s.get("target_base_id")
        father = s.get("father_serial")
        mother = s.get("mother_serial")

        # 校验 father 性别
        if father is not None:
            cursor.execute("SELECT gender FROM pet_instances WHERE serial_num = ?", (int(father),))
            row = cursor.fetchone()
            if not row:
                conn.close()
                raise HTTPException(status_code=400, detail=f"父方精灵 {father} 不存在")
            if row["gender"] == 2:
                conn.close()
                raise HTTPException(status_code=400, detail=f"父方精灵 {father} 性别为雌性，不能作为父方")

        # 校验 mother 性别
        if mother is not None:
            cursor.execute("SELECT gender FROM pet_instances WHERE serial_num = ?", (int(mother),))
            row = cursor.fetchone()
            if not row:
                conn.close()
                raise HTTPException(status_code=400, detail=f"母方精灵 {mother} 不存在")
            if row["gender"] == 1:
                conn.close()
                raise HTTPException(status_code=400, detail=f"母方精灵 {mother} 性别为雄性，不能作为母方")

        # 从 data 中读取配置字段（向后兼容旧请求）
        nature_id = s.get("nature_id")
        talents = s.get("talents")
        if talents is not None and not isinstance(talents, str):
            talents = json.dumps(talents, ensure_ascii=False)
        use_king_ball = 1 if s.get("use_king_ball") else 0
        king_ball_attr = s.get("king_ball_attr")
        breed_big_size = 1 if s.get("breed_big_size") else 0
        cursor.execute(
            "UPDATE breeding_slots SET target_base_id=?, father_serial=?, mother_serial=?, nature_id=?, talents=?, use_king_ball=?, king_ball_attr=?, breed_big_size=?, updated_at=datetime('now','localtime') WHERE slot_id=?",
            (target, int(father) if father else None, int(mother) if mother else None,
             nature_id, talents, use_king_ball, king_ball_attr, breed_big_size, sid)
        )

    conn.commit()
    conn.close()
    return {"msg": "ok"}


@app.post("/api/breeding_slots/add")
def add_breeding_slot(data: dict = Body(...)):
    """添加一个推荐方案到家园生蛋配置。

    查找第一个空槽位写入；如果目标精灵已存在某槽位，则覆盖该槽位。
    Body: {target_base_id, father_serial, mother_serial,
           nature_id, talents, use_king_ball, king_ball_attr, breed_big_size}
    """
    target_base_id = data.get("target_base_id")
    father_serial = data.get("father_serial")
    mother_serial = data.get("mother_serial")

    if not target_base_id or not father_serial or not mother_serial:
        raise HTTPException(status_code=400, detail="缺少必要参数")

    # 可选繁育参数
    nature_id = data.get("nature_id")
    talents = data.get("talents")
    if talents is not None and not isinstance(talents, str):
        talents = json.dumps(talents, ensure_ascii=False)
    use_king_ball = 1 if data.get("use_king_ball") else 0
    king_ball_attr = data.get("king_ball_attr")
    breed_big_size = 1 if data.get("breed_big_size") else 0

    conn = get_db_connection()
    cursor = conn.cursor()

    # 校验父方性别
    cursor.execute("SELECT gender FROM pet_instances WHERE serial_num = ?", (int(father_serial),))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail=f"父方精灵 {father_serial} 不存在")
    if row["gender"] == 2:
        conn.close()
        raise HTTPException(status_code=400, detail=f"父方精灵 {father_serial} 性别为雌性")

    # 校验母方性别
    cursor.execute("SELECT gender FROM pet_instances WHERE serial_num = ?", (int(mother_serial),))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail=f"母方精灵 {mother_serial} 不存在")
    if row["gender"] == 1:
        conn.close()
        raise HTTPException(status_code=400, detail=f"母方精灵 {mother_serial} 性别为雄性")

    # 查找目标精灵是否已占用某个槽位
    cursor.execute("SELECT slot_id FROM breeding_slots WHERE target_base_id = ?", (target_base_id,))
    existing = cursor.fetchone()

    if existing:
        slot_id = existing["slot_id"]
    else:
        # 查找第一个空槽位
        cursor.execute("SELECT slot_id FROM breeding_slots WHERE target_base_id IS NULL ORDER BY slot_id LIMIT 1")
        empty = cursor.fetchone()
        if empty:
            slot_id = empty["slot_id"]
        else:
            conn.close()
            raise HTTPException(status_code=409, detail="5个槽位已满，请先删除一个")

    cursor.execute(
        "UPDATE breeding_slots SET target_base_id=?, father_serial=?, mother_serial=?, nature_id=?, talents=?, use_king_ball=?, king_ball_attr=?, breed_big_size=?, updated_at=datetime('now','localtime') WHERE slot_id=?",
        (target_base_id, int(father_serial), int(mother_serial), nature_id, talents, use_king_ball, king_ball_attr, breed_big_size, slot_id)
    )
    conn.commit()
    conn.close()
    return {"slot_id": slot_id, "msg": "ok"}


@app.delete("/api/breeding_slots/{slot_id}")
def clear_breeding_slot(slot_id: int):
    """清空指定的家园生蛋槽位。"""
    if not (1 <= slot_id <= 5):
        raise HTTPException(status_code=400, detail="slot_id 必须在 1-5 之间")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE breeding_slots SET target_base_id=NULL, father_serial=NULL, mother_serial=NULL, nature_id=NULL, talents=NULL, use_king_ball=0, king_ball_attr=NULL, breed_big_size=0, updated_at=datetime('now','localtime') WHERE slot_id=?",
        (slot_id,)
    )
    conn.commit()
    conn.close()
    return {"msg": "ok"}


@app.get("/api/available_parents")
def get_available_parents():
    """获取所有可作为父母候选的精灵列表（不分槽位，前端自行去重）"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 所有 active 且已知性别的宠物
    cursor.execute("""
        SELECT i.serial_num, i.name, i.level, i.gender, i.talent_rank,
               b.egg_group_int, b.objId,
               n.name as nature_name
        FROM pet_instances i
        JOIN pet_base_info b ON i.base_id = b.objId
        LEFT JOIN pet_natures n ON i.nature = n.id
        WHERE i.is_active = 1 AND i.gender IN (1, 2)
        ORDER BY i.serial_num
    """)
    all_pets = [dict(r) for r in cursor.fetchall()]
    conn.close()

    males = [{
        "serial_num": p["serial_num"], "name": p["name"],
        "level": p["level"], "gender": p["gender"],
        "talent_rank": p["talent_rank"], "nature_name": p["nature_name"],
        "objId": p["objId"],
    } for p in all_pets if p["gender"] == 1]

    females = [{
        "serial_num": p["serial_num"], "name": p["name"],
        "level": p["level"], "gender": p["gender"],
        "talent_rank": p["talent_rank"], "nature_name": p["nature_name"],
        "objId": p["objId"],
    } for p in all_pets if p["gender"] == 2]

    return {"males": males, "females": females}


@app.get("/api/check_breeding_slots")
def check_breeding_slots():
    """检测所有已配置的繁育槽位是否需要更新推荐。对每个槽位重新跑推荐算法，
    比较当前最优父母与已选父母是否一致。"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pet_natures")
    natures_count = cursor.fetchone()[0] or 30

    cursor.execute("""
        SELECT s.*, b.evolutionId, b.name as target_name
        FROM breeding_slots s
        JOIN pet_base_info b ON s.target_base_id = b.objId
        WHERE s.target_base_id IS NOT NULL
          AND s.father_serial IS NOT NULL
          AND s.mother_serial IS NOT NULL
        ORDER BY s.slot_id
    """)
    slots = [dict(r) for r in cursor.fetchall()]

    results = []
    for slot in slots:
        target_evo_ids = set(json.loads(slot["evolutionId"]) if slot["evolutionId"] else [])
        slot_id = slot["slot_id"]
        current_father = slot["father_serial"]
        current_mother = slot["mother_serial"]

        # 查询母方候选（决定种族）
        cursor.execute("""
            SELECT i.*, b.familyId, b.egg_groups, b.evolutionId, b.name as base_name,
                   n.name as nature_name, n.plus_stat as nature_plus, n.minus_stat as nature_minus
            FROM pet_instances i
            JOIN pet_base_info b ON i.base_id = b.objId
            LEFT JOIN pet_natures n ON i.nature = n.id
            WHERE i.is_active = 1 AND i.gender != 1
        """)
        mothers = []
        for row in cursor.fetchall():
            d = dict(row)
            evo_ids = set(json.loads(d["evolutionId"]) if d["evolutionId"] else [])
            if evo_ids.issubset(target_evo_ids):
                mothers.append(d)

        # 父方候选
        cursor.execute("""
            SELECT i.*, b.familyId, b.egg_groups, b.evolutionId, b.name as base_name,
                   n.name as nature_name, n.plus_stat as nature_plus, n.minus_stat as nature_minus
            FROM pet_instances i
            JOIN pet_base_info b ON i.base_id = b.objId
            LEFT JOIN pet_natures n ON i.nature = n.id
            WHERE i.is_active = 1 AND i.gender != 2
        """)
        fathers = [dict(row) for row in cursor.fetchall()]

        # 打分，找到最优
        best_pair = None
        best_score = -1
        for mother in mothers:
            m_eggs = set(json.loads(mother["egg_groups"]) if mother["egg_groups"] else [])
            m_excellent = _get_excellent_stats(mother)
            for father in fathers:
                f_eggs = set(json.loads(father["egg_groups"]) if father["egg_groups"] else [])
                if not m_eggs.intersection(f_eggs):
                    continue
                f_excellent = _get_excellent_stats(father)
                calc = BreedCalculator(f_excellent, m_excellent, None)
                attr_prob = calc.get_target_prob([])
                total_prob = attr_prob * 1.0
                size_score = _get_size_score(mother) + _get_size_score(father) / 2
                score = round(total_prob * 100 + size_score * 50, 2)
                if score > best_score:
                    best_score = score
                    best_pair = {
                        "father_serial": father["serial_num"],
                        "father_name": father["base_name"],
                        "mother_serial": mother["serial_num"],
                        "mother_name": mother["base_name"],
                        "score": score,
                    }

        changed = not (
            best_pair
            and best_pair["father_serial"] == current_father
            and best_pair["mother_serial"] == current_mother
        ) if best_pair else False

        results.append({
            "slot_id": slot_id,
            "target_base_id": slot["target_base_id"],
            "target_name": slot["target_name"],
            "current_father_serial": current_father,
            "current_mother_serial": current_mother,
            "best_father_serial": best_pair["father_serial"] if best_pair else None,
            "best_father_name": best_pair["father_name"] if best_pair else None,
            "best_mother_serial": best_pair["mother_serial"] if best_pair else None,
            "best_mother_name": best_pair["mother_name"] if best_pair else None,
            "best_score": best_pair["score"] if best_pair else None,
            "changed": changed,
            "has_match": best_pair is not None,
        })

    conn.close()
    return results


@app.post("/api/sync")
def sync_pets():
    """Stream pet sync progress via SSE."""
    if not _sync_lock.acquire(blocking=False):
        _sync_logger.warning("同步被拒绝：已有任务在运行")
        raise HTTPException(status_code=409, detail="同步任务正在运行中")

    def event_stream():
        progress_queue = queue.Queue()

        def progress_callback(message, current=0, total=0):
            progress_queue.put({
                "message": message,
                "current": current,
                "total": total
            })

        def run_sync_task():
            try:
                from scripts.fetcher import run_sync
                result = run_sync(progress_callback=progress_callback)
                progress_queue.put({"done": True, "result": result})
                _sync_logger.info(f"同步完成：新增 {result.get('new', 0)} 只，更新 {result.get('updated', 0)} 只，共 {result.get('total', 0)} 只")
                fail_count = result.get("fail_count", 0)
                if fail_count:
                    for detail in result.get("fail_details", []):
                        _sync_logger.warning(f"  同步失败 -> {detail}")
            except Exception as e:
                _sync_logger.error(f"同步失败: {e}")
                progress_queue.put({"done": True, "error": str(e)})
            finally:
                _sync_lock.release()

        thread = threading.Thread(target=run_sync_task, daemon=True)
        thread.start()

        while True:
            try:
                msg = progress_queue.get(timeout=60)
            except queue.Empty:
                yield f"data: {json.dumps({'message': '心跳...', 'current': 0, 'total': 0})}\n\n"
                continue

            if msg.get("done"):
                if msg.get("error"):
                    yield f"data: {json.dumps({'error': msg['error']})}\n\n"
                else:
                    yield f"data: {json.dumps({'done': True, 'result': msg.get('result', {})})}\n\n"
                break
            else:
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/sync_status")
def get_sync_status():
    """Get sync cooldown status — always ready. Kept for frontend backward compat."""
    return {"cooldown_active": False, "can_sync": True}


@app.get("/api/refresh_time")
def get_refresh_time():
    """Get the stored pet refresh time."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'refresh_time'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"refresh_time": row[0]}
    return {"refresh_time": None}


# ---- 放生推荐 API ----

@app.get("/api/release_recommendations")
def get_release_recommendations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=5000),
    min_score: Optional[float] = Query(None),
    species_id: Optional[int] = Query(None)
):
    """
    获取放生推荐列表。

    实时计算每个品种内精灵的评分，按品种分组返回推荐放生的精灵。
    决策顺序：mutation变异保留 → 慈悲为怀保留 → 同乘优选 → 爱分享优选 → 常规评分排序。
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 加载用户的品种偏好配置
    cursor.execute("SELECT * FROM species_preferences")
    prefs_rows = cursor.fetchall()
    prefs = {}
    for row in prefs_rows:
        row_dict = dict(row)
        raw_ids = row_dict.get("preferred_nature_ids", "[]") or "[]"
        prefs[row["base_id"]] = {
            "preferred_nature_ids": json.loads(raw_ids),
            "keep_count": row["keep_count"],
        }

    # 2. 获取所有活跃精灵，按 base_id 分组
    cursor.execute("""
        SELECT i.*,
               b.name as base_name, b.description as base_description,
               b.familyId as base_familyId, b.egg_groups as base_egg_groups,
               b.egg_group_int as base_egg_group_int,
               b.evolutionStage as base_evolutionStage,
               b.evolutionId as base_evolutionId,
               b.height_high as base_height_high, b.height_low as base_height_low,
               b.weight_high as base_weight_high, b.weight_low as base_weight_low,
               n.name as nature_name, n.plus_stat as nature_plus, n.minus_stat as nature_minus
        FROM pet_instances i
        JOIN pet_base_info b ON i.base_id = b.objId
        LEFT JOIN pet_natures n ON i.nature = n.id
        WHERE i.is_active = 1
        ORDER BY b.name, i.serial_num
    """)
    all_rows = [dict(r) for r in cursor.fetchall()]

    # 3. 按进化链分组（同一家族不同形态放一起）
    species_groups = {}
    for r in all_rows:
        bid = r["base_id"]
        if species_id is not None and bid != species_id:
            continue
        # 用 evolutionId 作为家族分组 key，空数组则回退到 base_id
        evo_raw = r.get("base_evolutionId", "[]") or "[]"
        family_key = evo_raw if evo_raw != "[]" else str(bid)
        if family_key not in species_groups:
            species_groups[family_key] = {
                "base_id": bid,
                "species_name": r["base_name"],
                "base_info": {
                    "height_low": r["base_height_low"],
                    "height_high": r["base_height_high"],
                    "weight_low": r["base_weight_low"],
                    "weight_high": r["base_weight_high"],
                },
                "pets": [],
                "_member_stages": {},  # stage -> {base_id, name}
            }
        g = species_groups[family_key]
        stage = r.get("base_evolutionStage", 0) or 0
        if stage not in g["_member_stages"]:
            g["_member_stages"][stage] = {"base_id": bid, "name": r["base_name"]}
        g["pets"].append(r)

    # 修正组名：取 stage 最小的形态名称作为代表
    for g in species_groups.values():
        if g["_member_stages"]:
            min_stage = min(g["_member_stages"].keys())
            rep = g["_member_stages"][min_stage]
            g["base_id"] = rep["base_id"]
            g["species_name"] = rep["name"]
        # 生成 member_species 列表供前端展示
        g["member_species"] = sorted(
            [{"base_id": v["base_id"], "name": v["name"], "stage": k}
             for k, v in g["_member_stages"].items()],
            key=lambda x: x["stage"]
        )
        del g["_member_stages"]

    # 4. 对每个品种执行评分
    all_species_groups = []
    total_recommended = 0
    total_active = len(all_rows)
    kept_mercy = kept_ride = kept_share = 0

    for family_key, group in species_groups.items():
        # 查找家族偏好：遍历族内所有 base_id，优先用 stage-1 的配置
        pref = {"preferred_nature_ids": [], "keep_count": 3}
        configured = False
        for member in sorted(group["member_species"], key=lambda x: x["stage"]):
            member_pref = prefs.get(member["base_id"])
            if member_pref:
                pref = member_pref
                configured = True
                break

        result = compute_species_recommendations(
            group["pets"],
            group["base_info"],
            preferred_nature_ids=pref["preferred_nature_ids"],
            keep_count=pref["keep_count"],
        )

        # 统计特长保留数
        for p in group["pets"]:
            if p["serial_num"] in result["kept_serials"]:
                ts = p.get("talent_skill", 0)
                if ts == TALENT_SKILL_MERCY:
                    kept_mercy += 1
                elif ts == TALENT_SKILL_RIDE:
                    kept_ride += 1
                elif ts == TALENT_SKILL_SHARE:
                    kept_share += 1

        total_recommended += result["recommended_count"]

        # 组装返回数据（含宠物详细信息）
        pet_details = []
        for rp in result["pets"]:
            raw = next(p for p in group["pets"] if p["serial_num"] == rp["serial_num"])
            pet_details.append({
                "serial_num": rp["serial_num"],
                "name": raw["name"],
                "level": raw["level"],
                "gender": raw["gender"],
                "talent_rank": raw["talent_rank"],
                "nature": raw["nature"],
                "nature_name": raw.get("nature_name"),
                "nature_plus": raw.get("nature_plus"),
                "nature_minus": raw.get("nature_minus"),
                "talent_skill": raw["talent_skill"],
                "talent_skill_name": _get_talent_skill_name(raw["talent_skill"]),
                "mutation": raw.get("mutation", 0),
                "total_talent": sum(raw.get(f"{s}_talent", 0) for s in _STAT_COLS),
                **{f"{s}_talent": raw.get(f"{s}_talent", 0) for s in _STAT_COLS},
                "height": raw.get("height"),
                "weight": raw.get("weight"),
                "score": rp["score"],
                "reasons": rp["reasons"],
                "is_recommended": rp["is_recommended"],
                "is_kept": rp["is_kept"],
            })

        all_species_groups.append({
            "base_id": group["base_id"],
            "species_name": group["species_name"],
            "member_species": group["member_species"],
            "total_count": result["total_count"],
            "keep_count": result["keep_count"],
            "recommended_count": result["recommended_count"],
            "recommended_serials": result["recommended_serials"],
            "kept_serials": result["kept_serials"],
            "config": {
                "preferred_nature_ids": pref["preferred_nature_ids"],
                "keep_count": pref["keep_count"],
                "configured": configured,
            },
            "pets": pet_details,
        })

    conn.close()

    # 5. 分页
    total_species = len(all_species_groups)
    start = (page - 1) * page_size
    end = start + page_size
    page_groups = all_species_groups[start:end]

    return {
        "total": total_recommended,
        "page": page,
        "page_size": page_size,
        "total_species": total_species,
        "summary": {
            "total_active_pets": total_active,
            "total_recommended": total_recommended,
            "kept_by_mercy": kept_mercy,
            "kept_by_ride": kept_ride,
            "kept_by_share": kept_share,
        },
        "species_groups": page_groups,
    }


@app.get("/api/release_summary")
def get_release_summary():
    """获取放生推荐摘要（首页概览用）"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pet_instances WHERE is_active = 1")
    total_active = cursor.fetchone()[0] or 0

    cursor.execute("""
        SELECT i.serial_num, i.talent_skill, i.talent_rank, i.mutation
        FROM pet_instances i
        WHERE i.is_active = 1
    """)
    all_pets = cursor.fetchall()
    conn.close()

    rough_recommended = sum(
        1 for p in all_pets
        if p["talent_skill"] == 0 and p["talent_rank"] == 1 and p["mutation"] not in MUTATION_KEEP
    )

    total_active = max(total_active, 1)
    return {
        "total_active": total_active,
        "recommended_release": rough_recommended,
        "releaseable_percent": round(rough_recommended / total_active * 100, 1),
    }


@app.get("/api/species_preferences")
def get_species_preferences():
    """获取所有已配置的品种偏好。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sp.*, b.name as species_name
        FROM species_preferences sp
        LEFT JOIN pet_base_info b ON sp.base_id = b.objId
        ORDER BY b.name
    """)
    rows = cursor.fetchall()
    conn.close()
    return {
        "preferences": [
            {
                "base_id": r["base_id"],
                "species_name": r["species_name"],
                "preferred_nature_ids": json.loads((dict(r).get("preferred_nature_ids", "[]") or "[]")),
                "keep_count": r["keep_count"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    }


@app.put("/api/species_preferences")
def update_species_preferences(data: dict = Body(...)):
    """批量保存品种偏好配置。

    Body: {preferences: [{base_id, preferred_nature_ids, keep_count}, ...]}
    """
    prefs = data.get("preferences", [])
    if not prefs:
        raise HTTPException(status_code=400, detail="缺少 preferences 参数")

    conn = get_db_connection()
    cursor = conn.cursor()
    updated = 0
    for p in prefs:
        base_id = p.get("base_id")
        nature_ids = p.get("preferred_nature_ids", [])
        keep = p.get("keep_count", 3)
        if not base_id:
            continue
        nature_ids_json = json.dumps(nature_ids, ensure_ascii=False)
        cursor.execute("""
            INSERT INTO species_preferences (base_id, preferred_nature_ids, keep_count, updated_at)
            VALUES (?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(base_id) DO UPDATE SET
                preferred_nature_ids = excluded.preferred_nature_ids,
                keep_count = excluded.keep_count,
                updated_at = datetime('now','localtime')
        """, (base_id, nature_ids_json, keep))
        updated += 1

    conn.commit()
    conn.close()
    return {"msg": "ok", "updated": updated}


# 挂载前端静态文件
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
