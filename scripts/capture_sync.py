"""把已解密的精灵列表写入仓库。

实时流量由抓包记录页按 RocoMITM 改道读取。抓到 ZoneGetPetInfoByPageRsp 时调用这里的 upsert_pets。
导入 data/ 下已经解密的导出仍然可用。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

try:
    from scripts import fetcher
except ImportError:  # 直接运行本文件时
    import fetcher  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
KEY_DIR = PROJECT_ROOT / "captures" / "keys"
PET_LIST_OPCODE = 0x1346
PET_LIST_NAME = "ZoneGetPetInfoByPageRsp"
_sync_logger = logging.getLogger("sync")

_ATTRS = (
    ("hp", "hp"),
    ("attack", "adAttack"),
    ("special_attack", "apAttack"),
    ("defense", "adDefense"),
    ("special_defense", "apDefense"),
    ("speed", "speed"),
)


def decode_pet_name(value) -> str:
    """导出里的名字经常是 UTF-8 的十六进制。"""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if text and len(text) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in text):
        try:
            return bytes.fromhex(text).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return text
    return text


def _stat(block: dict | None, key: str) -> tuple[int, int, int]:
    node = (block or {}).get(key) or {}
    if not isinstance(node, dict):
        return 0, 0, 0
    return (
        int(node.get("base_value") or 0),
        int(node.get("total_race") or 0),
        int(node.get("talent") or 0),
    )


def _equipped_skills(pet: dict) -> list[int]:
    slots = [0, 0, 0, 0]
    overflow: list[int] = []
    skill = pet.get("skill") or {}
    for item in skill.get("skill_data") or []:
        if not isinstance(item, dict) or not item.get("is_equipped"):
            continue
        skill_id = int(item.get("id") or 0)
        pos = int(item.get("pos") or 0)
        if 1 <= pos <= 4 and slots[pos - 1] == 0:
            slots[pos - 1] = skill_id
        else:
            overflow.append(skill_id)
    for skill_id in overflow:
        for index, current in enumerate(slots):
            if current == 0:
                slots[index] = skill_id
                break
    return slots


def pet_record(pet: dict) -> dict | None:
    """把一条 PetData 收成 pet_instances 的列。"""
    if not isinstance(pet, dict) or pet.get("gid") is None:
        return None
    attrs = pet.get("attribute_info") or {}
    stats = {column: _stat(attrs, key) for key, column in _ATTRS}
    skills = _equipped_skills(pet)
    types = pet.get("skill_dam_type") or []
    if not isinstance(types, list):
        types = [types]
    medal = pet.get("wear_medal_conf_id")
    base_id = pet.get("base_conf_id") or pet.get("conf_id") or 0
    return {
        "serial_num": int(pet["gid"]),
        "base_id": int(base_id or 0),
        "name": decode_pet_name(pet.get("name")),
        "level": int(pet.get("level") or 0),
        "nature": int(pet.get("nature") or 0),
        "talent_rank": int(pet.get("talent_rank") or 0),
        "hp": stats["hp"][0],
        "adAttack": stats["adAttack"][0],
        "apAttack": stats["apAttack"][0],
        "adDefense": stats["adDefense"][0],
        "apDefense": stats["apDefense"][0],
        "speed": stats["speed"][0],
        "hp_race": stats["hp"][1],
        "adAttack_race": stats["adAttack"][1],
        "apAttack_race": stats["apAttack"][1],
        "adDefense_race": stats["adDefense"][1],
        "apDefense_race": stats["apDefense"][1],
        "speed_race": stats["speed"][1],
        "hp_talent": stats["hp"][2],
        "adAttack_talent": stats["adAttack"][2],
        "apAttack_talent": stats["apAttack"][2],
        "adDefense_talent": stats["adDefense"][2],
        "apDefense_talent": stats["apDefense"][2],
        "speed_talent": stats["speed"][2],
        "gender": int(pet.get("gender") or 0),
        "medal": "" if not medal else str(medal),
        "catch_ball": int(pet.get("ball_id") or 0),
        "height": int(pet.get("height") or 0),
        "weight": int(pet.get("weight") or 0),
        "bloodline": int(pet.get("blood_id") or 0),
        "skill_dam_type": json.dumps([int(item) for item in types if item is not None], ensure_ascii=False),
        "equip_skill_1": skills[0],
        "equip_skill_2": skills[1],
        "equip_skill_3": skills[2],
        "equip_skill_4": skills[3],
        "mutation": int(pet.get("mutation_type") or 0),
        "talent_skill": int(pet.get("speciality_id") or 0),
    }


class PetPageCollector:
    """按页攒 ZoneGetPetInfoByPageRsp。版本变了就丢掉上一版的半成品。"""

    def __init__(self) -> None:
        self.pets: dict[int, dict] = {}
        self.pages: set[int] = set()
        self.total_page: int | None = None
        self.version = None
        self._lock = threading.Lock()

    def add_decoded(self, decoded: dict) -> int:
        if not isinstance(decoded, dict):
            return 0
        version = decoded.get("version")
        with self._lock:
            if version is not None and self.version not in (None, version):
                self.pets.clear()
                self.pages.clear()
                self.total_page = None
            if version is not None:
                self.version = version
            page = decoded.get("req_page")
            total = decoded.get("total_page")
            if page is not None:
                self.pages.add(int(page))
            if total:
                self.total_page = int(total)
            added = 0
            info = decoded.get("pet_info") or {}
            rows = info.get("pet_data") if isinstance(info, dict) else None
            if rows is None and isinstance(decoded.get("pet_data"), list):
                rows = decoded["pet_data"]
            for pet in rows or []:
                record = pet_record(pet)
                if record is None:
                    continue
                self.pets[record["serial_num"]] = record
                added += 1
            return added

    def is_complete(self) -> bool:
        with self._lock:
            if not self.total_page or self.total_page <= 0:
                return False
            return set(range(1, self.total_page + 1)).issubset(self.pages)

    def status(self) -> tuple[int, int, int]:
        with self._lock:
            return len(self.pets), len(self.pages), int(self.total_page or 0)

    def snapshot(self) -> tuple[list[dict], bool]:
        with self._lock:
            complete = bool(self.total_page) and set(range(1, self.total_page + 1)).issubset(self.pages)
            return list(self.pets.values()), complete


def _pages_from_export(path: Path, collector: PetPageCollector) -> int:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        data = data.get("entries") or data.get("packets") or []
    added = 0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if entry.get("opcode_name") != PET_LIST_NAME and entry.get("opcode") not in (PET_LIST_OPCODE, "0x1346"):
            continue
        decoded = entry.get("decoded")
        if isinstance(decoded, dict):
            added += collector.add_decoded(decoded)
    return added


def export_files(filepath: str | None = None) -> list[Path]:
    if filepath:
        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        return [path]
    files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"data/ 下没有抓包导出 JSON（{DATA_DIR}）")
    return files


def _ensure_base_info(conn, base_ids: set[int], report) -> None:
    cursor = conn.cursor()
    missing = []
    for base_id in base_ids:
        if not base_id:
            continue
        cursor.execute("SELECT id FROM pet_base_info WHERE objId = ? OR id = ?", (base_id, base_id))
        if cursor.fetchone() is None:
            missing.append(base_id)
    if not missing:
        return
    conf_path = Path(fetcher.CONF_DIR) / "PETBASE_CONF.json"
    if not conf_path.is_file():
        report(f"未找到 {conf_path.name}，跳过种类补全", 0, 0)
        return
    with conf_path.open("r", encoding="utf-8") as handle:
        base_conf = {item["id"]: item for item in json.load(handle)}
    cursor.execute("SELECT group_id, group_name FROM egg_group_mapping")
    mapping = {row[0]: row[1] for row in cursor.fetchall()}
    for index, base_id in enumerate(missing, start=1):
        item = base_conf.get(base_id)
        if not item:
            report(f"配置里没有 base_id={base_id}", index, len(missing))
            continue
        groups = item.get("egg_group") or []
        group_names = [mapping.get(gid, f"未知组{gid}") for gid in groups]
        cursor.execute(
            """
            INSERT OR REPLACE INTO pet_base_info (
                id, name, description, hp, adAttack, apAttack, adDefense, apDefense, speed,
                familyId, itemId, objId, evolutionStage, evolutionId, egg_group_int, egg_groups,
                height_high, height_low, weight_high, weight_low
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item.get("name", ""),
                item.get("description", ""),
                item.get("hp_max_race", 0),
                item.get("phy_attack_race", 0),
                item.get("spe_attack_race", 0),
                item.get("phy_defence_race", 0),
                item.get("spe_defence_race", 0),
                item.get("speed_race", 0),
                json.dumps([], ensure_ascii=False),
                0,
                item["id"],
                item.get("stage", 0),
                json.dumps(item.get("pet_evolution_id", []), ensure_ascii=False),
                json.dumps(groups, ensure_ascii=False),
                json.dumps(group_names, ensure_ascii=False),
                item.get("height_high"),
                item.get("height_low"),
                item.get("weight_high"),
                item.get("weight_low"),
            ),
        )
        report(f"补全种类 {item.get('name', base_id)}", index, len(missing))
    conn.commit()


_COLUMNS = (
    "serial_num", "base_id", "name", "level", "nature", "talent_rank",
    "hp", "adAttack", "apAttack", "adDefense", "apDefense", "speed",
    "hp_race", "adAttack_race", "apAttack_race", "adDefense_race", "apDefense_race", "speed_race",
    "hp_talent", "adAttack_talent", "apAttack_talent", "adDefense_talent", "apDefense_talent", "speed_talent",
    "gender", "medal", "catch_ball", "height", "weight", "bloodline", "skill_dam_type",
    "equip_skill_1", "equip_skill_2", "equip_skill_3", "equip_skill_4", "mutation", "talent_skill",
)


def upsert_pets(records: list[dict], *, db_path: str | None = None, mark_missing: bool = False, progress=None) -> dict:
    def report(message, current=0, total=0):
        if progress:
            progress(message, current, total)

    if not records:
        report("没有可写入的精灵", 0, 0)
        return {"new": 0, "updated": 0, "total": 0, "released": 0, "complete": mark_missing}

    target = db_path or fetcher.DB_PATH
    previous = fetcher.DB_PATH
    fetcher.DB_PATH = target
    try:
        conn = fetcher.init_db()
    finally:
        fetcher.DB_PATH = previous

    _ensure_base_info(conn, {row["base_id"] for row in records}, report)
    cursor = conn.cursor()
    cursor.execute("SELECT serial_num FROM pet_instances")
    existing = {row[0] for row in cursor.fetchall()}
    new_count = 0
    updated_count = 0
    placeholders = ",".join("?" for _ in _COLUMNS)
    updates = ", ".join(f"{name}=excluded.{name}" for name in _COLUMNS if name != "serial_num")
    sql = (
        f"INSERT INTO pet_instances ({', '.join(_COLUMNS)}, is_active) VALUES ({placeholders}, 1) "
        f"ON CONFLICT(serial_num) DO UPDATE SET {updates}, is_active=1"
    )
    total = len(records)
    for index, record in enumerate(records, start=1):
        if record["serial_num"] in existing:
            updated_count += 1
        else:
            new_count += 1
            existing.add(record["serial_num"])
        cursor.execute(sql, tuple(record[name] for name in _COLUMNS))
        if index % 100 == 0 or index == total:
            report(f"写入 {index}/{total}", index, total)
    released = 0
    if mark_missing:
        captured = {row["serial_num"] for row in records}
        cursor.execute("SELECT serial_num FROM pet_instances WHERE is_active = 1")
        for (serial_num,) in cursor.fetchall():
            if serial_num not in captured:
                cursor.execute("UPDATE pet_instances SET is_active = 0 WHERE serial_num = ?", (serial_num,))
                released += 1
        if released:
            report(f"标记 {released} 只不在本次列表中的精灵为已放生", total, total)
    conn.commit()
    conn.close()
    report(f"完成：新增 {new_count}，更新 {updated_count}，共 {total}", total, total)
    return {
        "new": new_count,
        "updated": updated_count,
        "total": total,
        "released": released,
        "complete": mark_missing,
    }


def sync_from_export(filepath: str | None = None, progress=None, db_path: str | None = None) -> dict:
    def report(message, current=0, total=0):
        if progress:
            progress(message, current, total)

    files = export_files(filepath)
    collector = PetPageCollector()
    for path in files:
        report(f"读取 {path.name}", 0, 0)
        _pages_from_export(path, collector)
    records = collector.snapshot()[0]
    if not records:
        raise FileNotFoundError("导出里没有 ZoneGetPetInfoByPageRsp 精灵列表")
    page_text = f"{len(collector.pages)}/{collector.total_page or '?'}"
    report(f"解析到 {len(records)} 只，页 {page_text}", 0, len(records))
    report("导入只更新导出里出现的精灵，不会把库里其余精灵标成已放生", 0, len(records))
    result = upsert_pets(records, db_path=db_path, mark_missing=False, progress=progress)
    result["source"] = files[0].name if len(files) == 1 else f"{len(files)} 个文件"
    return result



def empty_capture_reason(engine) -> str:
    """没有写入精灵时，把传输层统计和原因拼成一行。"""
    hint = engine.failure_hint()
    if not hint and PET_LIST_OPCODE not in engine.opcodes:
        hint = "解密成功，但没有精灵列表。在游戏里打开宠物仓库并翻页。"
    if not hint:
        hint = "没有收集到可写入的精灵。"
    return f"{hint} {engine.summary()}"
