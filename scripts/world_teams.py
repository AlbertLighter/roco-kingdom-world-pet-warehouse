"""从登录包里的 PetTeamInfo 取出大世界三支队伍，并记到精灵库。"""

from __future__ import annotations

import sqlite3

from scripts.fetcher import DB_PATH

WORLD_TEAM_TYPE = 1


def _read_varint(data: bytes, index: int) -> tuple[int | None, int]:
    value = 0
    shift = 0
    while index < len(data) and shift <= 63:
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7
    return None, index


def _walk(data: bytes) -> list[tuple[int, int, object]]:
    fields = []
    index = 0
    while index < len(data):
        tag, nxt = _read_varint(data, index)
        if tag is None:
            break
        field = tag >> 3
        wire = tag & 7
        if field == 0 or field > 20000:
            break
        if wire == 0:
            value, nxt = _read_varint(data, nxt)
            if value is None:
                break
            fields.append((field, wire, value))
        elif wire == 2:
            length, nxt = _read_varint(data, nxt)
            if length is None or nxt + length > len(data):
                break
            fields.append((field, wire, data[nxt : nxt + length]))
            nxt += length
        elif wire == 1:
            if nxt + 8 > len(data):
                break
            nxt += 8
        elif wire == 5:
            if nxt + 4 > len(data):
                break
            nxt += 4
        else:
            break
        index = nxt
    return fields


def _pet_gid(blob: bytes) -> int | None:
    for field, wire, value in _walk(blob):
        if field == 1 and wire == 0 and isinstance(value, int):
            return value
    return None


def _parse_team(blob: bytes) -> list[int] | None:
    gids = []
    for field, wire, value in _walk(blob):
        if field == 2 and wire == 2 and isinstance(value, bytes):
            gid = _pet_gid(value)
            if gid:
                gids.append(gid)
    if len(gids) == 6:
        return gids
    return None


def _parse_team_info(blob: bytes) -> dict | None:
    teams = []
    team_type = None
    for field, wire, value in _walk(blob):
        if field == 2 and wire == 2 and isinstance(value, bytes):
            gids = _parse_team(value)
            if gids:
                teams.append(gids)
        elif field == 4 and wire == 0:
            team_type = value
    if team_type == WORLD_TEAM_TYPE and len(teams) == 3:
        return {"teams": teams}
    return None


def find_world_teams(data: bytes) -> list[list[int]] | None:
    """返回三支队伍，每支 6 个精灵编号。"""
    found: list[list[list[int]]] = []

    def visit(blob: bytes) -> None:
        for _field, wire, value in _walk(blob):
            if wire != 2 or not isinstance(value, bytes):
                continue
            info = _parse_team_info(value)
            if info:
                found.append(info["teams"])
            if len(value) > 24:
                visit(value)

    visit(data)
    return found[-1] if found else None


def ensure_world_team_columns(conn: sqlite3.Connection) -> None:
    for name, typedef in (("world_team", "INTEGER"), ("world_slot", "INTEGER")):
        try:
            conn.execute(f"ALTER TABLE pet_instances ADD COLUMN {name} {typedef}")
        except sqlite3.OperationalError:
            pass


def apply_world_teams(body: bytes, db_path: str | None = None) -> dict:
    """用登录包刷新大世界队伍标记。找不到三支满编队伍时不改原标记。"""
    teams = find_world_teams(body)
    if not teams:
        return {"updated": 0, "missing": []}
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        ensure_world_team_columns(conn)
        conn.execute("UPDATE pet_instances SET world_team = NULL, world_slot = NULL WHERE world_team IS NOT NULL")
        missing = []
        updated = 0
        for team_no, gids in enumerate(teams, start=1):
            for slot, gid in enumerate(gids, start=1):
                cursor = conn.execute(
                    "UPDATE pet_instances SET world_team = ?, world_slot = ?, is_active = 1 WHERE serial_num = ?",
                    (team_no, slot, gid),
                )
                if cursor.rowcount:
                    updated += 1
                else:
                    missing.append(gid)
        conn.commit()
        return {"updated": updated, "missing": missing, "teams": teams}
    finally:
        conn.close()
