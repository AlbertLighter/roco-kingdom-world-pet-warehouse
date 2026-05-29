import json
import os
import time
import sqlite3

# Support both direct execution and import from backend
try:
    from api_client import (
        gateway_request,
        fetch_user_info,
        fetch_refresh_time,
        fetch_base_info
    )
except ImportError:
    from scripts.api_client import (
        gateway_request,
        fetch_user_info,
        fetch_refresh_time,
        fetch_base_info
    )

# Resolve paths relative to project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "warehouse.db")
CONF_DIR = os.path.join(PROJECT_ROOT, "roco_kingdom_world_conf")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
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
        gender INTEGER DEFAULT 0, -- 0: unknown, 1: male, 2: female
        medal TEXT,
        catch_ball INTEGER,
        height INTEGER,
        weight INTEGER,
        FOREIGN KEY (base_id) REFERENCES pet_base_info (id)
    )
    """)

    # Migration checks
    try:
        cursor.execute("ALTER TABLE pet_instances ADD COLUMN is_active INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_instances ADD COLUMN gender INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_instances ADD COLUMN medal TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_instances ADD COLUMN catch_ball INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_instances ADD COLUMN height INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_instances ADD COLUMN weight INTEGER")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE pet_base_info ADD COLUMN itemId INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_base_info ADD COLUMN objId INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_base_info ADD COLUMN evolutionStage INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_base_info ADD COLUMN evolutionId TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_base_info ADD COLUMN egg_groups TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_base_info ADD COLUMN egg_group_int INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_base_info ADD COLUMN height_high INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_base_info ADD COLUMN height_low INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_base_info ADD COLUMN weight_high INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pet_base_info ADD COLUMN weight_low INTEGER")
    except sqlite3.OperationalError:
        pass

    # Create pet_natures table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pet_natures (
        id INTEGER PRIMARY KEY,
        name TEXT,
        plus_stat TEXT,
        minus_stat TEXT
    )
    """)

    # Seed pet_natures data
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

    # Create settings table for key-value storage
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Create egg_group_mapping table (egg_group_int ID -> name)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS egg_group_mapping (
        group_id INTEGER PRIMARY KEY,
        group_name TEXT NOT NULL
    )
    """)

    # Seed egg group mapping data
    egg_group_mapping = [
        (1, "无法孵蛋"),
        (2, "巨灵组"),
        (3, "两栖组"),
        (4, "昆虫组"),
        (5, "天空组"),
        (6, "动物组"),
        (7, "妖精组"),
        (8, "植物组"),
        (9, "拟人组"),
        (10, "软体组"),
        (11, "大地组"),
        (12, "魔力组"),
        (13, "海洋组"),
        (14, "龙组"),
        (15, "机械组"),
    ]
    cursor.executemany("INSERT OR REPLACE INTO egg_group_mapping (group_id, group_name) VALUES (?, ?)", egg_group_mapping)

    conn.commit()
    return conn

def run_sync(progress_callback=None):
    """
    Run the pet sync process. progress_callback(message, current, total) is called
    to report progress. If None, prints to stdout.
    """
    def report(message, current=0, total=0):
        if progress_callback:
            progress_callback(message, current, total)
        else:
            print(message)

    conn = init_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check login
    report("正在检查登录状态...", 0, 0)
    user_info = fetch_user_info()
    if user_info:
        report(f"已登录: {user_info.get('nickName', 'Unknown')}", 0, 0)
    else:
        report("⚠ 获取用户信息失败，请检查 token 配置", 0, 0)

    # Show refresh time
    refresh_info = fetch_refresh_time()
    if refresh_info:
        next_refresh = refresh_info.get('next_auto_refresh_time', 0)
        refresh_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(next_refresh))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                       ("refresh_time", refresh_time_str))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                       ("refresh_deadline", str(next_refresh)))
        conn.commit()
        report(f"宠物刷新时间: {refresh_time_str}", 0, 0)

    # 同步基础配置数据 (从 roco_kingdom_world_conf/PETBASE_CONF.json)
    try:
        conf_path = os.path.join(CONF_DIR, 'PETBASE_CONF.json')
        with open(conf_path, 'r', encoding='utf-8') as f:
            base_conf = json.load(f)
            for data in base_conf:
                egg_group = data.get("egg_group", [])
                pid = data.get("id")
                if pid is None:
                    continue
                cursor.execute("""
                UPDATE pet_base_info SET
                    egg_group_int = ?,
                    height_high = ?,
                    height_low = ?,
                    weight_high = ?,
                    weight_low = ?
                WHERE objId = ?
                """, (
                    json.dumps(egg_group, ensure_ascii=False),
                    data.get("height_high"),
                    data.get("height_low"),
                    data.get("weight_high"),
                    data.get("weight_low"),
                    int(pid)
                ))
        conn.commit()

        # Generate egg_groups from egg_group_int using mapping table
        cursor.execute("SELECT group_id, group_name FROM egg_group_mapping")
        mapping = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT id, egg_group_int FROM pet_base_info WHERE egg_group_int IS NOT NULL")
        for row in cursor.fetchall():
            pet_id = row[0]
            try:
                group_int_list = json.loads(row[1]) if row[1] else []
                group_names = [mapping.get(gid, f"未知组{gid}") for gid in group_int_list]
                cursor.execute("UPDATE pet_base_info SET egg_groups = ? WHERE id = ?",
                               (json.dumps(group_names, ensure_ascii=False), pet_id))
            except (json.JSONDecodeError, TypeError):
                pass
        conn.commit()
        report("基础配置已同步", 0, 0)
    except Exception as e:
        report(f"⚠ 基础配置同步失败: {e}", 0, 0)

    # Fetch pet list (paginated)
    current_page = 1
    page_size = 100
    all_api_pets = []
    all_api_serials = set()

    report("正在获取精灵列表...", 0, 0)
    while True:
        report(f"正在获取列表第 {current_page} 页...", 0, 0)
        list_data = gateway_request("/api/pet/list", {
            "page": current_page,
            "pageSize": page_size,
            "searchKeyword": "",
            "manual": False,
            "sort": [{"field": "Count", "order": "desc"}],
            "baseid": ""
        })

        if not list_data or not list_data.get("list"):
            break

        for item in list_data["list"]:
            sn = int(item["SerialNum"])
            all_api_serials.add(sn)
            all_api_pets.append({
                "SerialNum": sn,
                "PetBaseId": item["PetBaseId"],
                "PetTalentRank": item.get("PetTalentRank", 0)
            })

        if len(list_data["list"]) < page_size:
            break
        current_page += 1
        time.sleep(0.3)

    total_pets = len(all_api_serials)
    report(f"共发现 {total_pets} 只精灵", 0, total_pets)

    # 1. 补全缺失的 PetBaseId 基础信息
    unique_base_ids = {pet["PetBaseId"] for pet in all_api_pets}
    missing_ids = []
    for baseid in unique_base_ids:
        cursor.execute("SELECT id FROM pet_base_info WHERE objId = ?", (baseid,))
        if not cursor.fetchone():
            missing_ids.append(baseid)

    for i, baseid in enumerate(missing_ids):
        report(f"补全基础信息 {baseid} ({i+1}/{len(missing_ids)})", i+1, len(missing_ids))
        base_info = fetch_base_info(baseid)
        if base_info:
            fid_raw = base_info.get("familyId", "")
            family_ids = [int(x) for x in str(fid_raw).split(';') if str(x).strip()] if fid_raw else []
            eid_raw = base_info.get("evolutionId", "")
            evolution_ids = [int(x) for x in str(eid_raw).split(';') if str(x).strip()] if eid_raw else []

            cursor.execute("""
            INSERT OR REPLACE INTO pet_base_info (id, name, description, hp, adAttack, apAttack, adDefense, apDefense, speed, familyId, itemId, objId, evolutionStage, evolutionId)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                base_info["id"],
                base_info["name"],
                base_info.get("desc", ""),
                base_info["hp"],
                base_info["adAttack"],
                base_info["apAttack"],
                base_info["adDefense"],
                base_info["apDefense"],
                base_info["speed"],
                json.dumps(family_ids, ensure_ascii=False),
                int(base_info.get("itemId", 0)),
                int(base_info.get("objId", 0)),
                base_info.get("evolutionStage", 0),
                json.dumps(evolution_ids, ensure_ascii=False)
            ))
            conn.commit()
            time.sleep(0.5)

    # 2. Detect and mark released pets
    cursor.execute("SELECT serial_num FROM pet_instances WHERE is_active = 1")
    db_active_serials = {row[0] for row in cursor.fetchall()}

    released_serials = db_active_serials - all_api_serials
    if released_serials:
        report(f"检测到 {len(released_serials)} 只已放生精灵，标记中...", 0, 0)
        for sn in released_serials:
            cursor.execute("UPDATE pet_instances SET is_active = 0 WHERE serial_num = ?", (sn,))
        conn.commit()

    # 3. Reactivate/Ensure active for current pets
    for sn in all_api_serials:
        cursor.execute("UPDATE pet_instances SET is_active = 1 WHERE serial_num = ?", (sn,))
    conn.commit()

    # 4. Fetch details for new pets or pets missing new fields
    new_count = 0
    updated_count = 0

    # Pre-scan to find pets that need detail fetching
    needs_detail = []
    for pet in all_api_pets:
        sn = pet["SerialNum"]
        trank = pet["PetTalentRank"]
        cursor.execute("SELECT height, catch_ball FROM pet_instances WHERE serial_num = ?", (sn,))
        row = cursor.fetchone()

        if row:
            cursor.execute("UPDATE pet_instances SET talent_rank = ? WHERE serial_num = ?", (trank, sn))
            if row["height"] is None or row["catch_ball"] is None:
                needs_detail.append((pet, "update"))
        else:
            needs_detail.append((pet, "new"))

    conn.commit()
    detail_total = len(needs_detail)
    report(f"需要获取详情的精灵: {detail_total} 只", 0, detail_total)

    for i, (pet, action) in enumerate(needs_detail):
        sn = pet["SerialNum"]
        trank = pet["PetTalentRank"]

        if action == "update":
            report(f"更新精灵 #{sn} 详情 ({i+1}/{detail_total})", i+1, detail_total)
        else:
            report(f"获取新精灵 #{sn} 详情 ({i+1}/{detail_total})", i+1, detail_total)

        detail = gateway_request("/api/pet/detail", {"id": str(sn)})
        if detail:
            if action == "update":
                cursor.execute("""
                UPDATE pet_instances SET
                    medal = ?, catch_ball = ?, height = ?, weight = ?
                WHERE serial_num = ?
                """, (
                    detail.get("PetMedal", ""),
                    detail.get("PetCatchBall", 0),
                    detail.get("PetHeight", 0),
                    detail.get("PetWeight", 0),
                    sn
                ))
                updated_count += 1
            else:
                cursor.execute("""
                INSERT INTO pet_instances (
                    serial_num, base_id, name, level, nature, talent_rank,
                    hp, adAttack, apAttack, adDefense, apDefense, speed,
                    hp_race, adAttack_race, apAttack_race, adDefense_race, apDefense_race, speed_race,
                    hp_talent, adAttack_talent, apAttack_talent, adDefense_talent, apDefense_talent, speed_talent,
                    is_active, gender, medal, catch_ball, height, weight
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?)
                """, (
                    int(detail["SerialNum"]),
                    detail["PetBaseId"],
                    detail["PetName"],
                    detail["SpiritLevel"],
                    detail.get("PetNature", 0),
                    trank,
                    detail["MaxHp"],
                    detail["PhyAttack"],
                    detail["MagAttack"],
                    detail["PhyDefense"],
                    detail["MagDefense"],
                    detail["Speed"],
                    detail.get("MaxHpRace", 0),
                    detail.get("PhyAttackRace", 0),
                    detail.get("MagAttackRace", 0),
                    detail.get("PhyDefenseRace", 0),
                    detail.get("MagDefenseRace", 0),
                    detail.get("SpeedRace", 0),
                    detail.get("MaxHpTalent", 0),
                    detail.get("PhyAttackTalent", 0),
                    detail.get("MagAttackTalent", 0),
                    detail.get("PhyDefenseTalent", 0),
                    detail.get("MagDefenseTalent", 0),
                    detail.get("SpeedTalent", 0),
                    detail.get("PetMedal", ""),
                    detail.get("PetCatchBall", 0),
                    detail.get("PetHeight", 0),
                    detail.get("PetWeight", 0)
                ))
                new_count += 1
            conn.commit()
            time.sleep(1)

    summary = f"同步完成！新增 {new_count} 只，更新 {updated_count} 只"
    report(summary, detail_total, detail_total)
    conn.close()
    return {"new": new_count, "updated": updated_count, "total": total_pets}


if __name__ == "__main__":
    run_sync()
