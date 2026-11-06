import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import requests
from fastapi import HTTPException

import backend.main as app
import scripts.fetcher as fetcher
from scripts.capture_sync import (
    WarehouseSnapshotError,
    import_warehouse_snapshot,
    pet_record,
    upsert_pets,
)
from scripts.fetcher import init_db
from scripts.packet_store import record_divert
from scripts.warehouse_push import (
    describe_push,
    import_endpoint,
    push_warehouse_snapshot,
    save_warehouse_snapshot,
    start_warehouse_push,
)


def sample_pet(**overrides):
    pet = {
        "gid": 42,
        "base_conf_id": 3005,
        "name": "测试",
        "level": 12,
        "voice": 87,
        "gender": 2,
    }
    pet.update(overrides)
    return pet


class _Response:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload


class WarehouseImportTests(unittest.TestCase):
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

    def test_pet_record_shape_and_raw_pet_data_round_trip(self):
        imported = import_warehouse_snapshot(
            {"pets": [pet_record(sample_pet()), sample_pet(gid=7, name="另一只")], "complete": False},
            db_path=self.db_path,
        )
        self.assertEqual(imported["total"], 2)
        self.assertEqual(imported["released"], 0)
        self.assertFalse(imported["complete"])
        conn = sqlite3.connect(self.db_path)
        rows = {
            row[0]: row
            for row in conn.execute("SELECT serial_num, name, voice, is_active FROM pet_instances")
        }
        conn.close()
        self.assertEqual(rows[42][1], "测试")
        self.assertEqual(rows[42][2], 87)
        self.assertEqual(rows[7][1], "另一只")

    def test_complete_snapshot_releases_absent_pets_but_keeps_world_team(self):
        upsert_pets(
            [pet_record(sample_pet(gid=7, name="旧")), pet_record(sample_pet(gid=8, name="队"))],
            db_path=self.db_path,
            mark_missing=False,
        )
        conn = sqlite3.connect(self.db_path)
        conn.execute("ALTER TABLE pet_instances ADD COLUMN world_team INTEGER")
        conn.execute("UPDATE pet_instances SET world_team = 1 WHERE serial_num = 8")
        conn.commit()
        conn.close()

        released = import_warehouse_snapshot(
            {"pets": [pet_record(sample_pet())]},
            db_path=self.db_path,
        )
        self.assertTrue(released["complete"])
        self.assertEqual(released["released"], 1)
        conn = sqlite3.connect(self.db_path)
        active = dict(conn.execute("SELECT serial_num, is_active FROM pet_instances"))
        conn.close()
        self.assertEqual(active[7], 0)
        self.assertEqual(active[8], 1)
        self.assertEqual(active[42], 1)

    def test_empty_snapshot_does_not_release_the_warehouse(self):
        upsert_pets([pet_record(sample_pet(gid=7))], db_path=self.db_path, mark_missing=False)
        result = import_warehouse_snapshot({"pets": [], "complete": True}, db_path=self.db_path)
        self.assertEqual(result["released"], 0)
        conn = sqlite3.connect(self.db_path)
        active = conn.execute("SELECT is_active FROM pet_instances WHERE serial_num = 7").fetchone()[0]
        conn.close()
        self.assertEqual(active, 1)

    def test_bad_row_is_rejected_before_write(self):
        with self.assertRaises(WarehouseSnapshotError):
            import_warehouse_snapshot({"pets": ["nope"]}, db_path=self.db_path)
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM pet_instances").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_http_import_uses_the_server_database(self):
        with mock.patch.object(app, "DB_PATH", self.db_path):
            result = app.api_sync_warehouse({"complete": False, "pets": [pet_record(sample_pet())]})
        self.assertEqual(result["new"], 1)
        with mock.patch.object(app, "DB_PATH", self.db_path):
            with self.assertRaises(HTTPException) as caught:
                app.api_sync_warehouse({"nope": []})
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("pets", caught.exception.detail)


class WarehousePushTests(unittest.TestCase):
    def test_endpoint_accepts_a_full_url_or_a_base_url(self):
        self.assertEqual(import_endpoint("https://example.com/"), "https://example.com/api/sync/warehouse")
        self.assertEqual(
            import_endpoint("https://example.com/api/sync/warehouse/"),
            "https://example.com/api/sync/warehouse",
        )

    def test_push_retries_network_errors_then_succeeds(self):
        calls = {"n": 0}

        def poster(endpoint, payload, token):
            calls["n"] += 1
            self.assertEqual(endpoint, "https://cloud.example/api/sync/warehouse")
            self.assertEqual(token, "secret")
            self.assertTrue(payload["complete"])
            self.assertEqual(payload["pets"][0]["serial_num"], 9)
            if calls["n"] < 3:
                raise requests.ConnectionError("down")
            return _Response(200, {"new": 1, "updated": 0, "released": 2})

        result = push_warehouse_snapshot(
            [{"serial_num": 9}],
            environ={"ROCO_CLOUD_URL": "https://cloud.example", "ROCO_SYNC_TOKEN": "secret"},
            poster=poster,
            sleep=lambda _delay: None,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(calls["n"], 3)
        self.assertIn("标记放生 2", describe_push(result, 1))

    def test_auth_failure_is_not_retried(self):
        calls = {"n": 0}

        def poster(_endpoint, _payload, _token):
            calls["n"] += 1
            return _Response(401, {"detail": "需要本机令牌或同步令牌"})

        result = push_warehouse_snapshot(
            [{"serial_num": 9}],
            environ={"ROCO_CLOUD_URL": "https://cloud.example", "ROCO_SYNC_TOKEN": "secret"},
            poster=poster,
            sleep=lambda _delay: None,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(calls["n"], 1)
        self.assertIn("同步令牌", result["reason"])

    def test_missing_cloud_url_skips_without_posting(self):
        def poster(*_args):
            raise AssertionError("should not post")

        result = push_warehouse_snapshot([{"serial_num": 1}], environ={}, poster=poster)
        self.assertTrue(result["skipped"])

    def test_start_push_writes_a_snapshot_before_the_request(self):
        seen = {}

        def poster(_endpoint, payload, _token):
            seen["pets"] = payload["pets"]
            return _Response(200, {"new": 1, "updated": 0, "released": 0})

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "warehouse_snapshot.json"
            thread = start_warehouse_push(
                [pet_record(sample_pet())],
                environ={"ROCO_CLOUD_URL": "https://cloud.example", "ROCO_SYNC_TOKEN": "secret"},
                poster=poster,
                sleep=lambda _delay: None,
                snapshot_path=path,
            )
            thread.join(2)
            self.assertFalse(thread.is_alive())
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["pets"][0]["serial_num"], 42)
            self.assertTrue(thread.push_result["result"]["ok"])
            self.assertEqual(seen["pets"][0]["serial_num"], 42)
            again = save_warehouse_snapshot(saved["pets"], path)
            self.assertTrue(again.is_file())


class DivertPushHookTests(unittest.TestCase):
    def test_complete_warehouse_starts_a_push_and_partial_list_does_not(self):
        started = []

        def relay(_seconds, _on_s2c, progress=None, on_frame=None):
            del progress
            on_frame("s2c", 0x1346, 0x1346, b"\x01", "list")
            return {"key": True, "s2c": 1, "failed": 0}

        def fake_start(records, emit=None):
            started.append(list(records))
            if emit:
                emit("已推送")
            holder = {"result": {"ok": True, "skipped": True}}
            thread = threading.Thread(target=lambda: None)
            thread.push_result = holder
            thread.start()
            return thread

        decoded = {
            "total_page": 1,
            "req_page": 1,
            "pet_info": {"pet_data": [sample_pet(gid=9)]},
        }
        relay_mod = mock.Mock()
        relay_mod.run_relay.side_effect = relay
        with (
            mock.patch.dict(sys.modules, {"scripts.game_relay": relay_mod}),
            mock.patch("scripts.packet_store.record_message", return_value=True),
            mock.patch("scripts.rocom_pet.parse_pet_list", return_value=decoded),
            mock.patch(
                "scripts.capture_sync.upsert_pets",
                return_value={"new": 1, "updated": 0, "released": 1, "total": 1},
            ) as upsert,
            mock.patch("scripts.warehouse_push.start_warehouse_push", side_effect=fake_start),
        ):
            result = record_divert()
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0][0]["serial_num"], 9)
        self.assertTrue(upsert.call_args.kwargs["mark_missing"])
        self.assertTrue(result["sync"]["push"]["ok"])

        started.clear()
        partial = {
            "total_page": 2,
            "req_page": 1,
            "pet_info": {"pet_data": [sample_pet(gid=9)]},
        }
        relay_mod.run_relay.side_effect = relay
        with (
            mock.patch.dict(sys.modules, {"scripts.game_relay": relay_mod}),
            mock.patch("scripts.packet_store.record_message", return_value=True),
            mock.patch("scripts.rocom_pet.parse_pet_list", return_value=partial),
            mock.patch(
                "scripts.capture_sync.upsert_pets",
                return_value={"new": 1, "updated": 0, "released": 0, "total": 1},
            ) as upsert,
            mock.patch("scripts.warehouse_push.start_warehouse_push", side_effect=fake_start),
        ):
            result = record_divert()
        self.assertEqual(started, [])
        self.assertFalse(upsert.call_args.kwargs["mark_missing"])
        self.assertNotIn("push", result["sync"])


if __name__ == "__main__":
    unittest.main()
