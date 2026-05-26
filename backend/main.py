import sqlite3
import json
import itertools
import queue
import threading
import sys
import os
import time
from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List

# Add project root to path so we can import scripts
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = FastAPI()

# Global lock to prevent concurrent sync runs
_sync_lock = threading.Lock()

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "warehouse.db"

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

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
    
    # 基础过滤条件
    where_clauses = ["1=1"]
    params = []
    
    if not include_inactive:
        where_clauses.append("i.is_active = 1")
    
    if name:
        where_clauses.append("(i.name LIKE ? OR b.name LIKE ?)")
        params.extend([f"%{name}%", f"%{name}%"])
    
    if base_id:
        where_clauses.append("i.base_id = ?")
        params.append(base_id)
    
    where_str = " AND ".join(where_clauses)
    
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

@app.post("/api/recommend_parents")
def recommend_parents(
    target_base_id: int = Body(...),
    desired_nature_id: Optional[int] = Body(None),
    desired_stats: List[str] = Body([]),
    use_king_ball: bool = Body(False),
    king_ball_attr: Optional[str] = Body(None),
    breed_big_size: bool = Body(False)
):
    """
    推荐父母逻辑:
    1. 目标精灵 evolutionStage 必须为 1
    2. 母方: gender=2, 进化链包含目标精灵的 evolutionId
    3. 父方: gender=1, 与母方属于相同蛋组
    4. 计算具体概率而非模糊评分
    5. 支持大块头体型倾向
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取性格总数用于计算随机概率
    cursor.execute("SELECT COUNT(*) FROM pet_natures")
    natures_count = cursor.fetchone()[0] or 30
    
    # 1. 获取目标精灵信息
    cursor.execute("SELECT * FROM pet_base_info WHERE objId = ?", (target_base_id,))
    target = cursor.fetchone()
    if not target or target["evolutionStage"] != 1:
        raise HTTPException(status_code=400, detail="Target must be base form (stage 1)")
    
    target_evo_ids = set(json.loads(target["evolutionId"]) if target["evolutionId"] else [])
    
    # 2. 找到所有合格的母方
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
    all_females = cursor.fetchall()
    qualified_mothers = []
    for f in all_females:
        f_dict = dict(f)
        m_evo_ids = set(json.loads(f_dict["evolutionId"]) if f_dict["evolutionId"] else [])
        if m_evo_ids.issubset(target_evo_ids):
            qualified_mothers.append(f_dict)

    # 3. 找到所有合格的父方
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

    recommendations = []
    stat_cols = {
        "hp": "hp_talent",
        "adAttack": "adAttack_talent",
        "apAttack": "apAttack_talent",
        "adDefense": "adDefense_talent",
        "apDefense": "apDefense_talent",
        "speed": "speed_talent"
    }
    
    def get_size_score(p):
        h = p.get("height") or 0
        hl = p.get("base_height_low") or 0
        hh = p.get("base_height_high") or 1
        w = p.get("weight") or 0
        wl = p.get("base_weight_low") or 0
        wh = p.get("base_weight_high") or 1
        
        hs = (h - hl) / (hh - hl) if hh > hl else 0
        ws = (w - wl) / (wh - wl) if wh > wl else 0
        return max(0, min(1, (hs + ws) / 2))

    for mother in qualified_mothers:
        m_eggs = set(json.loads(mother["egg_groups"]) if mother["egg_groups"] else [])
        m_excellent = [k for k, col in stat_cols.items() if mother.get(col, 0) > 0][:3]
        
        for father in all_males:
            f_eggs = set(json.loads(father["egg_groups"]) if father["egg_groups"] else [])
            if not m_eggs.intersection(f_eggs):
                continue
            
            f_excellent = [k for k, col in stat_cols.items() if father.get(col, 0) > 0][:3]
            
            # 属性继承概率
            calc = BreedCalculator(f_excellent, m_excellent, king_ball_attr if use_king_ball else None)
            attr_prob = calc.get_target_prob(desired_stats)
            
            # 性格继承概率
            nature_prob = 1.0
            if desired_nature_id:
                p = 0
                if father["nature"] == desired_nature_id: p += 0.35
                if mother["nature"] == desired_nature_id: p += 0.35
                p += 0.3 * (1.0 / natures_count)
                nature_prob = p
            
            total_prob = attr_prob * nature_prob
            
            score = round(total_prob * 100, 2)
            
            size_score = 0
            if breed_big_size:
                size_score = (get_size_score(mother) + get_size_score(father)) / 2
                score = round(total_prob * 100 + size_score * 50, 2) # 体型分最高加50分，影响排序

            # 获取完整的母方和父方数据，用于前端渲染卡片
            mother_full = dict(mother)
            mother_full["name"] = mother["base_name"] # 确保 name 字段存在
            
            father_full = dict(father)
            father_full["name"] = father["base_name"]

            recommendations.append({
                "mother": mother_full,
                "father": father_full,
                "probability": total_prob,
                "size_score": round(size_score * 100, 2) if breed_big_size else 0,
                "score": score
            })

    # 按概率(或综合评分)排序
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
