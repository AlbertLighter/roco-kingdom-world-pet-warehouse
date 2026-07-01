import sqlite3
import json
import itertools
import queue
import threading
import sys
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List

# Add project root to path so we can import scripts
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))




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
        with open(path, "r", encoding="utf-8") as f:
            _config_cache[filename] = json.load(f)
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
        (1, "大胆", "物防", "物攻"), (2, "固执", "物攻", "魔攻"), (3, "调皮", "物攻", "魔抗"),
        (4, "勇敢", "物攻", "速度"), (5, "逞强", "物攻", "生命"), (6, "稳重", "魔攻", "物防"),
        (7, "天真", "速度", "魔抗"), (8, "懒散", "物防", "魔防"), (9, "悠闲", "物防", "速度"),
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

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

_STAT_COLS = {
    "hp": "hp_talent",
    "adAttack": "adAttack_talent",
    "apAttack": "apAttack_talent",
    "adDefense": "adDefense_talent",
    "apDefense": "apDefense_talent",
    "speed": "speed_talent"
}


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

@app.post("/api/sync")
def sync_pets():
    """Stream pet sync progress via SSE."""
    # Check cooldown based on pet refresh time
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'refresh_deadline'")
    row = cursor.fetchone()
    conn.close()

    if row:
        deadline = float(row[0])
        remaining = deadline - time.time()
        if remaining > 0:
            deadline_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(deadline))
            raise HTTPException(status_code=429, detail={
                "message": f"宠物尚未刷新，刷新时间: {deadline_str}",
                "remaining_seconds": int(remaining)
            })

    if not _sync_lock.acquire(blocking=False):
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
            except Exception as e:
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
    """Get sync cooldown status based on pet refresh time."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'refresh_deadline'")
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"cooldown_active": False, "can_sync": True}

    deadline = float(row[0])
    remaining = deadline - time.time()

    if remaining <= 0:
        return {"cooldown_active": False, "can_sync": True}

    return {
        "cooldown_active": True,
        "can_sync": False,
        "remaining_seconds": int(remaining)
    }


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


# 挂载前端静态文件
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
