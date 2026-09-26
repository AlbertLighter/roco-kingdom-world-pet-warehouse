"""保存解密后的应用层消息，供抓包页面查看、解析和序列化。"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from scripts.rocom_pet import parse_pet_list, scan_fields

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "captures" / "packets.db"
DATA_DIR = PROJECT_ROOT / "data"
MAX_ROWS = 3000
MAX_BODY = 256 * 1024
PET_LIST_OPCODE = 0x1346

_LOCK = threading.Lock()
_sync_logger = logging.getLogger("sync")

OPCODE_NAMES = {
    0x0102: "ZoneLoginRsp",
    0x0133: "ZoneSceneMoveReq",
    0x01AE: "ZonePetEvoluteRsp",
    0x01C5: "ZonePetFreeRsp",
    0x0243: "ZoneGoodsRewardNotify",
    0x030C: "ZoneCrackEggRsp",
    0x0403: "ZoneUpdatePetCollectTagRsp",
    0x1345: "ZoneGetPetInfoByPageReq",
    0x1346: "ZoneGetPetInfoByPageRsp",
    0x132C: "ZoneBattleFinishNotify",
    0x141E: "ZonePetMedalCommonRsp",
    0x1808: "ZoneTogetherCatchPetForGiftingRsp",
    0x1883: "ZonePetBoxUnlockRsp",
    0x1888: "ZonePetBoxChangePetRsp",
    0x1891: "ZonePetBoxSettingUpRsp",
    0x1893: "ZonePetBoxSetMarkTypeRsp",
    0x1983: "ZoneSceneThrowCatchFinishRsp",
}


def opcode_name(opcode: int) -> str:
    return OPCODE_NAMES.get(int(opcode), f"0x{int(opcode):04X}")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS capture_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            direction TEXT,
            opcode INTEGER,
            opcode_hex TEXT,
            opcode_name TEXT,
            session TEXT,
            source TEXT,
            body_len INTEGER,
            truncated INTEGER DEFAULT 0,
            app_body_hex TEXT,
            summary TEXT,
            decoded_json TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_capture_opcode ON capture_messages(opcode)")
    return conn


def _trim(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS n FROM capture_messages").fetchone()
    extra = int(row["n"]) - MAX_ROWS
    if extra > 0:
        conn.execute(
            "DELETE FROM capture_messages WHERE id IN (SELECT id FROM capture_messages ORDER BY id ASC LIMIT ?)",
            (extra,),
        )


def _summary(opcode: int, body: bytes) -> str:
    if opcode != PET_LIST_OPCODE or not body:
        return ""
    try:
        decoded = parse_pet_list(body)
    except Exception:
        return "宠物列表"
    pets = (decoded.get("pet_info") or {}).get("pet_data") or []
    return f"宠物列表 第 {decoded.get('req_page', '?')}/{decoded.get('total_page', '?')} 页，{len(pets)} 只"


def record_message(message, source: str = "live", summary: str | None = None) -> int | None:
    body = bytes(getattr(message, "app_body", b"") or b"")
    truncated = 0
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY]
        truncated = 1
    opcode = int(getattr(message, "opcode", 0))
    try:
        with _LOCK:
            conn = _connect()
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO capture_messages (
                        ts, direction, opcode, opcode_hex, opcode_name, session, source,
                        body_len, truncated, app_body_hex, summary, decoded_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        getattr(message, "direction", ""),
                        opcode,
                        f"0x{opcode:04X}",
                        opcode_name(opcode),
                        getattr(message, "session", ""),
                        source,
                        len(bytes(getattr(message, "app_body", b"") or b"")),
                        truncated,
                        body.hex(),
                        summary or _summary(opcode, body),
                    ),
                )
                _trim(conn)
                conn.commit()
                return int(cursor.lastrowid)
            finally:
                conn.close()
    except Exception:
        return None


def _row_brief(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "ts": row["ts"],
        "direction": row["direction"],
        "opcode": row["opcode"],
        "opcode_hex": row["opcode_hex"],
        "opcode_name": row["opcode_name"],
        "session": row["session"],
        "source": row["source"],
        "body_len": row["body_len"],
        "truncated": row["truncated"],
        "summary": row["summary"] or "",
        "parsed": bool(row["decoded_json"]),
    }


def list_messages(page: int = 1, page_size: int = 40, direction: str = "", opcode: str = "", q: str = "") -> dict:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    clauses = []
    args: list = []
    if direction in ("c2s", "s2c"):
        clauses.append("direction = ?")
        args.append(direction)
    if opcode:
        text = opcode.strip().lower()
        if text.startswith("0x"):
            clauses.append("opcode = ?")
            args.append(int(text, 16))
        elif text.isdigit():
            clauses.append("opcode = ?")
            args.append(int(text))
        else:
            clauses.append("opcode_name LIKE ?")
            args.append(f"%{opcode.strip()}%")
    if q:
        clauses.append("(summary LIKE ? OR session LIKE ? OR opcode_name LIKE ?)")
        like = f"%{q.strip()}%"
        args.extend([like, like, like])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with _LOCK:
        conn = _connect()
        try:
            total = conn.execute(f"SELECT COUNT(*) AS n FROM capture_messages{where}", args).fetchone()["n"]
            rows = conn.execute(
                f"SELECT * FROM capture_messages{where} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*args, page_size, (page - 1) * page_size],
            ).fetchall()
        finally:
            conn.close()
    return {"total": total, "page": page, "pageSize": page_size, "data": [_row_brief(row) for row in rows]}


def get_message(message_id: int) -> dict | None:
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM capture_messages WHERE id = ?", (message_id,)).fetchone()
        finally:
            conn.close()
    if row is None:
        return None
    item = _row_brief(row)
    item["app_body_hex"] = row["app_body_hex"] or ""
    if row["decoded_json"]:
        item["decoded"] = json.loads(row["decoded_json"])
    return item


def clear_messages() -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM capture_messages")
            conn.commit()
        finally:
            conn.close()


def _try_text(blob: bytes) -> str:
    if not blob or len(blob) > 200:
        return ""
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text):
        return ""
    return text


def wire_tree(body: bytes, depth: int = 0) -> list:
    if depth >= 4:
        return [{"field": 0, "note": "已达展开层数", "hex": body[:32].hex()}]
    nodes = []
    for field_no, wire, value in scan_fields(body):
        node: dict = {"field": field_no, "wire": wire}
        if wire == 0 and isinstance(value, int):
            node["value"] = value
        elif wire == 2 and isinstance(value, (bytes, bytearray)):
            raw = bytes(value)
            text = _try_text(raw)
            nested = scan_fields(raw) if depth < 3 and raw else []
            if nested and not text and nested[0][0] <= 500:
                node["message"] = wire_tree(raw, depth + 1)
            else:
                node["len"] = len(raw)
                node["hex"] = raw[:48].hex()
                if text:
                    node["text"] = text
        else:
            node["hex"] = value.hex() if isinstance(value, (bytes, bytearray)) else str(value)
        nodes.append(node)
    return nodes


def parse_body(opcode: int, body: bytes) -> dict:
    parsed: dict = {"opcode": opcode, "opcode_hex": f"0x{opcode:04X}", "opcode_name": opcode_name(opcode)}
    if opcode == PET_LIST_OPCODE:
        parsed["decoded"] = parse_pet_list(body)
        parsed["kind"] = "pet_list"
    else:
        parsed["decoded"] = {"fields": wire_tree(body)}
        parsed["kind"] = "wire"
    return parsed


def parse_message(message_id: int) -> dict:
    item = get_message(message_id)
    if item is None:
        raise KeyError(message_id)
    body = bytes.fromhex(item.get("app_body_hex") or "")
    parsed = parse_body(int(item["opcode"]), body)
    encoded = json.dumps(parsed, ensure_ascii=False)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("UPDATE capture_messages SET decoded_json = ? WHERE id = ?", (encoded, message_id))
            conn.commit()
        finally:
            conn.close()
    parsed["id"] = message_id
    return parsed


def serialize_message(message_id: int) -> dict:
    item = get_message(message_id)
    if item is None:
        raise KeyError(message_id)
    if "decoded" not in item:
        parsed = parse_message(message_id)
    else:
        parsed = item["decoded"]
        if "kind" not in parsed:
            parsed = {"kind": "stored", "decoded": parsed, "opcode": item["opcode"], "opcode_name": item["opcode_name"]}
    export_entry = {
        "direction": item["direction"],
        "opcode_hex": item["opcode_hex"],
        "opcode_name": item["opcode_name"],
        "payload_hex": item.get("app_body_hex") or "",
        "decoded": parsed.get("decoded"),
        "decode_status": "ok",
    }
    return {
        "id": message_id,
        "json": json.dumps(parsed, ensure_ascii=False, indent=2),
        "export_entry": export_entry,
    }


def import_export_file(path: Path) -> int:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        data = data.get("entries") or data.get("packets") or []
    saved = 0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        opcode = entry.get("opcode")
        if isinstance(opcode, str) and opcode.lower().startswith("0x"):
            opcode = int(opcode, 16)
        elif opcode is None and entry.get("opcode_hex"):
            opcode = int(str(entry["opcode_hex"]), 16)
        if not isinstance(opcode, int):
            continue
        payload = entry.get("payload_hex") or ""
        try:
            body = bytes.fromhex(payload) if payload else b""
        except ValueError:
            body = b""

        class _Msg:
            direction = entry.get("direction") or ""
            app_body = body
            session = path.name

        _Msg.opcode = opcode
        message_id = record_message(_Msg(), source=path.name)
        if not message_id:
            continue
        saved += 1
        if entry.get("decoded") is not None:
            summary = _summary(opcode, body) or str(entry.get("opcode_name") or "")
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute(
                        "UPDATE capture_messages SET decoded_json = ?, summary = ? WHERE id = ?",
                        (json.dumps({"kind": "import", "decoded": entry["decoded"]}, ensure_ascii=False), summary, message_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
    return saved


def record_divert(seconds: int | None = None, progress=None) -> dict:
    """改道读取游戏连接，只把解密后的下行消息记到抓包页。"""
    from scripts.game_relay import run_relay
    from scripts.rocom_capture import Message

    def report(message, current=0, total=0):
        if progress:
            progress(message, current, total)

    saved = {"n": 0}

    def emit(message: str, current: int = 0, total: int = 0) -> None:
        _sync_logger.info("抓包 %s", message)
        report(message, current, total)

    from scripts.capture_sync import PET_LIST_OPCODE, PetPageCollector, pet_record, upsert_pets
    from scripts.rocom_pet import parse_pet_list

    collector = PetPageCollector()
    sync_result = {"new": 0, "updated": 0, "total": 0, "released": 0}
    marked = {"done": False}

    def on_frame(direction: str, command: int, opcode: int | None, payload: bytes, note: str) -> None:
        shown = opcode if opcode is not None else command
        text = note or None
        message = Message(direction, shown, "divert", payload, payload)
        if record_message(message, source="divert", summary=text):
            saved["n"] += 1
            if saved["n"] == 1 or saved["n"] % 25 == 0:
                emit(f"已记录 {saved['n']} 条", saved["n"], 0)
        if direction == "s2c" and opcode == 0x0102 and payload:
            from scripts.pet_boxes import apply_boxes
            from scripts.world_teams import apply_world_teams

            marked = apply_world_teams(payload)
            if marked.get("updated"):
                emit(f"已标记大世界队伍 {marked['updated']} 只", saved["n"], 0)
            boxes = apply_boxes(payload)
            if boxes.get("updated"):
                emit(f"已记录盒子位置 {boxes['updated']} 只，{boxes['boxes']} 个盒子", saved["n"], 0)
            return
        if direction == "s2c" and opcode == 0x01C5 and payload:
            from scripts.pet_boxes import mark_freed

            freed = mark_freed(payload)
            if freed:
                emit(f"监听到放生成功 {freed} 只，已从仓库标出", saved["n"], 0)
        if direction != "s2c" or opcode != PET_LIST_OPCODE or not payload:
            return
        decoded = parse_pet_list(payload)
        added = collector.add_decoded(decoded)
        records = [row for pet in (decoded.get("pet_info") or {}).get("pet_data") or [] if (row := pet_record(pet))]
        if not records:
            return
        complete = collector.is_complete() and not marked["done"]
        if complete:
            marked["done"] = True
            all_records, _done = collector.snapshot()
            result = upsert_pets(all_records, mark_missing=True, progress=emit)
        else:
            result = upsert_pets(records, mark_missing=False, progress=emit)
        sync_result["new"] += result.get("new", 0)
        sync_result["updated"] += result.get("updated", 0)
        sync_result["released"] = result.get("released", 0)
        count, pages, total_page = collector.status()
        sync_result["total"] = count
        emit(
            f"精灵列表 +{added}，已写入仓库：新增 {result.get('new', 0)}，更新 {result.get('updated', 0)}，页 {pages}/{total_page or '?'}",
            count,
            total_page,
        )

    emit("正在把游戏的 8195 改道到本机。请在这之后进入游戏。抓到精灵列表会自动写入仓库。点停止记录后结束。")
    stats = run_relay(seconds, lambda _opcode, _payload: None, progress=emit, on_frame=on_frame)
    summary = (
        f"改道记录 密钥={'有' if stats.get('key') else '无'}，"
        f"下行 {stats.get('s2c', 0)}，解密失败 {stats.get('failed', 0)}"
    )
    if stats.get("fail_reason"):
        summary = f"{summary}。{stats['fail_reason']}"
    emit(summary, saved["n"], saved["n"])
    if saved["n"] == 0 and not stats.get("key"):
        emit("没有拿到 0x1002 会话密钥。用管理员启动服务，先点改道记录，再进入游戏。", 0, 0)
    emit(f"记录结束，共 {saved['n']} 条", saved["n"], saved["n"])
    return {
        "saved": saved["n"],
        "no_key": 0 if stats.get("key") else 1,
        "bad_key": stats.get("failed", 0),
        "summary": summary,
        "sync": sync_result if sync_result.get("total") else None,
    }


def record_live(mode: str, iface: str = "", seconds: int = 120, pcap: str = "", progress=None) -> dict:
    """回放 pcap，只记解密后的消息。"""
    from scripts.rocom_capture import Engine, FileKeyStore, read_pcap

    def report(message, current=0, total=0):
        if progress:
            progress(message, current, total)

    saved = {"n": 0}

    def emit(message: str, current: int = 0, total: int = 0) -> None:
        _sync_logger.info("抓包 %s", message)
        report(message, current, total)

    def on_message(message) -> None:
        if record_message(message, source="pcap" if mode == "pcap" else "live"):
            saved["n"] += 1
            if saved["n"] == 1 or saved["n"] % 25 == 0:
                emit(f"已记录 {saved['n']} 条", saved["n"], 0)

    engine = Engine(
        port=8195,
        keys=FileKeyStore(PROJECT_ROOT / "captures" / "keys"),
        on_message=on_message,
        log=lambda message: emit(message, saved["n"], 0),
    )
    if mode != "pcap":
        raise ValueError("实时记录只走改道。回放请使用 pcap。")
    path = Path(pcap)
    if not path.is_file():
        raise FileNotFoundError(f"pcap 不存在: {path}")
    emit(f"回放 {path}", 0, 0)
    for packet in read_pcap(path):
        engine.feed(packet)
    summary = engine.summary()
    emit(summary, saved["n"], saved["n"])
    if saved["n"] == 0:
        emit(engine.failure_hint() or "没有解出应用层消息。", saved["n"], saved["n"])
    emit(f"记录结束，共 {saved['n']} 条", saved["n"], saved["n"])
    return {
        "saved": saved["n"],
        "no_key": engine.no_key,
        "bad_key": engine.bad_key,
        "summary": summary,
    }


def import_exports() -> dict:
    files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"data/ 下没有 JSON 导出（{DATA_DIR}）")
    saved = 0
    for path in files:
        saved += import_export_file(path)
    return {"files": len(files), "saved": saved}
