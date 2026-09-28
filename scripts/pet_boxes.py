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


def _trusted_boxes(boxes: dict[int, list[int]], known: set[int]) -> dict[int, list[int]]:
    """至少三盒、且每盒已占用格子里 60% 的编号本地已有，才当成一份可写入的快照。"""
    kept = {}
    for box_id, gids in boxes.items():
        occupied = [gid for gid in gids if gid]
        if not occupied:
            continue
        if sum(gid in known for gid in occupied) < len(occupied) * 0.6:
            continue
        kept[box_id] = gids
    if len(kept) < 3:
        return {}
    return kept


def apply_boxes(body: bytes, db_path: str | None = None) -> dict:
    """用登录或整理回包刷新盒子。只改这次认出来的盒子，认不全时保留原位置。"""
    boxes = find_boxes(body)
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        ensure_box_columns(conn)
        known = {row[0] for row in conn.execute("SELECT serial_num FROM pet_instances")}
        kept = _trusted_boxes(boxes, known)
        if not kept:
            return {"boxes": 0, "updated": 0}
        updated = 0
        for box_id in kept:
            conn.execute(
                "UPDATE pet_instances SET box_id = NULL, box_slot = NULL WHERE box_id = ?",
                (box_id,),
            )
        for box_id, gids in kept.items():
            for slot, gid in enumerate(gids):
                if not gid or gid not in known:
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


def _change_fields(blob: bytes) -> list[tuple[int, int]] | None:
    """PetBoxPetChange 只有 1–4 号 varint。半截或带更后面字段的都不是。"""
    if not blob or len(blob) > 40:
        return None
    fields = []
    index = 0
    while index < len(blob):
        tag, nxt = _read_varint(blob, index)
        if tag is None:
            return None
        field = tag >> 3
        wire = tag & 7
        if field == 0 or field > 4 or wire != 0:
            return None
        value, nxt = _read_varint(blob, nxt)
        if value is None:
            return None
        fields.append((field, value))
        index = nxt
    return fields


def _as_move(blob: bytes) -> tuple[int, int, int] | None:
    parsed = _change_fields(blob)
    if not parsed:
        return None
    values = {field: value for field, value in parsed}
    gid = values.get(1) or 0
    in_team = values.get(2, 0)
    box_id = values.get(3)
    pos = values.get(4)
    if gid < 1000 or in_team not in (0, 1) or in_team:
        return None
    if box_id is None or pos is None:
        return None
    if not (1 <= box_id <= 80 and 1 <= pos <= 30):
        return None
    return gid, box_id, pos - 1


def find_box_moves(data: bytes) -> list[tuple[int, int, int]]:
    """0x1888 里的落位：(精灵编号, 盒子, 0 起的格子)。"""
    found: list[tuple[int, int, int]] = []

    def visit(blob: bytes, depth: int = 0) -> None:
        if depth > 8:
            return
        move = _as_move(blob)
        if move:
            found.append(move)
            return
        for _field, wire, value in _walk(blob):
            if wire == 2 and isinstance(value, bytes) and len(value) >= 2:
                visit(value, depth + 1)

    visit(data)
    return found


def apply_box_moves(
    body: bytes,
    db_path: str | None = None,
    only_gids: set[int] | None = None,
) -> dict:
    """按换位回包改单只精灵的格子，不清掉这次没出现的盒子。"""
    moves = find_box_moves(body)
    if only_gids is not None:
        moves = [item for item in moves if item[0] in only_gids]
    if not moves:
        return {"updated": 0, "moves": 0}
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        ensure_box_columns(conn)
        known = {row[0] for row in conn.execute("SELECT serial_num FROM pet_instances")}
        updated = 0
        for gid, box_id, slot in moves:
            if gid not in known:
                continue
            conn.execute(
                """
                UPDATE pet_instances
                SET box_id = NULL, box_slot = NULL
                WHERE box_id = ? AND box_slot = ? AND serial_num != ?
                """,
                (box_id, slot, gid),
            )
            cursor = conn.execute(
                "UPDATE pet_instances SET box_id = ?, box_slot = ? WHERE serial_num = ?",
                (box_id, slot, gid),
            )
            updated += cursor.rowcount
        conn.commit()
        return {"updated": updated, "moves": len(moves)}
    finally:
        conn.close()


def gifted_gid(payload: bytes) -> int:
    """赠送执行确认里的精灵编号。带完整精灵数据的是预览，返回 0。"""
    from scripts.rocom_pet import find_live_pets

    if find_live_pets(payload):
        return 0
    result = None
    gid = 0
    for field, wire, value in _walk(payload):
        if field == 1 and wire == 2 and isinstance(value, bytes):
            for sub_field, sub_wire, sub_value in _walk(value):
                if sub_field == 1 and sub_wire == 0 and isinstance(sub_value, int):
                    result = sub_value
        elif field == 3 and wire == 0 and isinstance(value, int):
            gid = value
    if result != 0 or gid <= 0:
        return 0
    return gid


def mark_gifted(payload: bytes, db_path: str | None = None) -> int:
    gid = gifted_gid(payload)
    if not gid:
        return 0
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        ensure_box_columns(conn)
        cursor = conn.execute(
            """
            UPDATE pet_instances
            SET is_active = 0, box_id = NULL, box_slot = NULL
            WHERE serial_num = ? AND is_active = 1
            """,
            (gid,),
        )
        conn.commit()
        return cursor.rowcount
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
