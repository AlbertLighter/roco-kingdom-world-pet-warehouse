"""从登录包的 PetBox 记下每个精灵在仓库格子里的位置。"""

from __future__ import annotations

import sqlite3

from scripts.fetcher import DB_PATH
from scripts.world_teams import _read_varint, _walk


def _packed_ints(blob: bytes) -> list[int]:
    values = []
    index = 0
    while index < len(blob):
        value, index = _read_varint(blob, index)
        if value is None:
            return []
        values.append(value)
    return values


def _as_box(blob: bytes) -> tuple[int, list[int]] | None:
    box_id = None
    gids: list[int] = []
    for field, wire, value in _walk(blob):
        if field == 1 and wire == 0 and isinstance(value, int):
            box_id = value
        elif field == 3 and wire == 0 and isinstance(value, int):
            gids.append(value)
        elif field == 3 and wire == 2 and isinstance(value, bytes):
            gids.extend(_packed_ints(value))
    if box_id is None or not (1 <= box_id <= 80):
        return None
    if not (1 <= len(gids) <= 30):
        return None
    return box_id, gids


def find_boxes(data: bytes) -> dict[int, list[int]]:
    """盒子编号 → 从左到右、从上到下的精灵编号。"""
    found: dict[int, list[int]] = {}

    def visit(blob: bytes, depth: int = 0) -> None:
        if depth > 8:
            return
        for _field, wire, value in _walk(blob):
            if wire != 2 or not isinstance(value, bytes):
                continue
            box = _as_box(value)
            if box and len(box[1]) > len(found.get(box[0], [])):
                found[box[0]] = box[1]
            if len(value) > 16:
                visit(value, depth + 1)

    visit(data)
    return found


def ensure_box_columns(conn: sqlite3.Connection) -> None:
    for name, typedef in (("box_id", "INTEGER"), ("box_slot", "INTEGER")):
        try:
            conn.execute(f"ALTER TABLE pet_instances ADD COLUMN {name} {typedef}")
        except sqlite3.OperationalError:
            pass


def apply_boxes(body: bytes, db_path: str | None = None) -> dict:
    boxes = find_boxes(body)
    plausible = {box_id: gids for box_id, gids in boxes.items() if len(gids) >= 10}
    if len(plausible) < 3:
        return {"boxes": 0, "updated": 0}
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        ensure_box_columns(conn)
        known = {row[0] for row in conn.execute("SELECT serial_num FROM pet_instances")}
        kept = {
            box_id: gids
            for box_id, gids in plausible.items()
            if sum(gid in known for gid in gids) >= len(gids) * 0.6
        }
        if len(kept) < 3:
            return {"boxes": 0, "updated": 0}
        conn.execute("UPDATE pet_instances SET box_id = NULL, box_slot = NULL WHERE box_id IS NOT NULL")
        updated = 0
        for box_id, gids in kept.items():
            for slot, gid in enumerate(gids):
                if gid not in known:
                    continue
                cursor = conn.execute(
                    "UPDATE pet_instances SET box_id = ?, box_slot = ? WHERE serial_num = ?",
                    (box_id, slot, gid),
                )
                updated += cursor.rowcount
        conn.commit()
        return {"boxes": len(kept), "updated": updated}
    finally:
        conn.close()


def freed_gids(payload: bytes) -> list[int]:
    """ZonePetFreeRsp 里服务器确认放生的编号。"""
    gids = []
    for field, wire, value in _walk(payload):
        if field != 2:
            continue
        if wire == 0 and isinstance(value, int):
            gids.append(value)
        elif wire == 2 and isinstance(value, bytes):
            gids.extend(_packed_ints(value))
    return gids


def mark_freed(payload: bytes, db_path: str | None = None) -> int:
    gids = freed_gids(payload)
    if not gids:
        return 0
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        updated = 0
        for gid in gids:
            cursor = conn.execute(
                "UPDATE pet_instances SET is_active = 0 WHERE serial_num = ? AND is_active = 1",
                (gid,),
            )
            updated += cursor.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()
