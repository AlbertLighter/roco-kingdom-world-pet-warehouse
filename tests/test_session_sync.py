import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import scripts.fetcher as fetcher
from scripts.capture_sync import apply_captured_event, pet_record, upsert_pets
from scripts.fetcher import init_db
from scripts.rocom_pet import find_live_pets


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def _msg(field: int, blob: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(blob)) + blob


def _field(field: int, value: int) -> bytes:
    return _varint((field << 3) | 0) + _varint(value)


def _pet(gid: int, add_time: int | None = None) -> bytes:
    body = _field(1, gid) + _field(2, 2000671) + _msg(3, "小蓝灵".encode())
    body += _field(10, 20) + _field(15, 3005)
    if add_time is not None:
        body += _field(32, add_time)
    return body


class SessionSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "warehouse.db")
        previous = fetcher.DB_PATH
        fetcher.DB_PATH = self.db_path
        try:
            init_db().close()
        finally:
            fetcher.DB_PATH = previous

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_evolution_updates_one_pet_and_leaves_the_rest(self):
        upsert_pets(
            [pet_record({"gid": 7, "conf_id": 2000671, "base_conf_id": 3005, "name": "旧"})],
            db_path=self.db_path,
        )
        event = apply_captured_event(0x01AE, _msg(6, _pet(42)), db_path=self.db_path)
        self.assertEqual(event["new"], 1)
        conn = sqlite3.connect(self.db_path)
        rows = {
            row[0]: row[1:]
            for row in conn.execute("SELECT serial_num, base_id, level, is_active FROM pet_instances")
        }
        conn.close()
        self.assertEqual(rows[42], (3005, 20, 1))
        self.assertEqual(rows[7][2], 1)

    def test_battle_finish_ignores_an_old_pet(self):
        now = int(time.time())
        body = _msg(6, _pet(2001, add_time=now)) + _msg(6, _pet(2002, add_time=100))
        found = find_live_pets(body, max_add_age=180, now=now)
        self.assertEqual([pet["gid"] for pet in found], [2001])
        event = apply_captured_event(0x132C, body, db_path=self.db_path)
        self.assertEqual(event["new"], 1)
        conn = sqlite3.connect(self.db_path)
        serials = {row[0] for row in conn.execute("SELECT serial_num FROM pet_instances")}
        conn.close()
        self.assertIn(2001, serials)
        self.assertNotIn(2002, serials)

    def test_gift_ack_marks_inactive_and_preview_does_not(self):
        upsert_pets(
            [pet_record({"gid": 3001, "conf_id": 2000671, "base_conf_id": 3005, "name": "赠"})],
            db_path=self.db_path,
        )
        preview = _msg(1, _field(1, 0)) + _field(3, 3001) + _msg(6, _pet(3001))
        self.assertEqual(apply_captured_event(0x1808, preview, db_path=self.db_path)["updated"], 0)
        ack = _msg(1, _field(1, 0)) + _field(3, 3001)
        self.assertEqual(apply_captured_event(0x1808, ack, db_path=self.db_path)["updated"], 1)
        conn = sqlite3.connect(self.db_path)
        active, box_id = conn.execute("SELECT is_active, box_id FROM pet_instances WHERE serial_num = 3001").fetchone()
        conn.close()
        self.assertEqual(active, 0)
        self.assertIsNone(box_id)


if __name__ == "__main__":
    unittest.main()
