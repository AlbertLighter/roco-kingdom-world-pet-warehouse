import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import backend.main as app
from scripts.game_release_click import steps_between
from scripts.natures import nature_rows


class ReleaseNavigationTests(unittest.TestCase):
    def test_gap_clicks_cover_the_boxes_in_between(self):
        self.assertEqual(steps_between(None, 1), 0)
        self.assertEqual(steps_between(1, 2), 1)
        self.assertEqual(steps_between(1, 3), 2)

    def test_backward_or_same_box_is_rejected(self):
        with self.assertRaises(ValueError):
            steps_between(3, 3)
        with self.assertRaises(ValueError):
            steps_between(3, 1)


class SchemaTests(unittest.TestCase):
    def test_fresh_database_creates_breeding_columns_before_use(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = str(Path(directory.name) / "warehouse.db")
        old = app.DB_PATH
        app.DB_PATH = path
        try:
            app.init_db()
        finally:
            app.DB_PATH = old
        conn = sqlite3.connect(path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(breeding_slots)")}
        natures = {
            row[0]: (row[1], row[2])
            for row in conn.execute("SELECT id, plus_stat, minus_stat FROM pet_natures WHERE id IN (1, 6, 7)")
        }
        conn.close()
        self.assertTrue({"nature_id", "talents", "use_king_ball", "king_ball_attr", "breed_big_size"} <= columns)
        self.assertEqual(natures[1], ("物攻", "物防"))
        self.assertEqual(natures[6], ("物防", "物攻"))
        self.assertEqual(natures[7], ("物防", "魔攻"))

    def test_nature_file_is_the_only_source(self):
        rows = {item[0]: item[2:] for item in nature_rows(app.CONF_DIR)}
        self.assertEqual(rows[1], ("物攻", "物防"))
        self.assertEqual(rows[6], ("物防", "物攻"))
        self.assertEqual(rows[7], ("物防", "魔攻"))
        self.assertNotEqual(rows[7], ("速度", "魔防"))


class BreedingScoreTests(unittest.TestCase):
    def test_unknown_gender_empty_family_and_self_pair_are_rejected(self):
        unknown = {
            "serial_num": 1,
            "gender": 0,
            "egg_groups": '["植物组"]',
            "evolutionId": "[]",
            "nature": 1,
            "base_name": "未知",
        }
        self.assertIsNone(
            app.score_breeding_pair(unknown, dict(unknown, serial_num=2), [], None, 30, False, None, False)
        )
        self.assertFalse(app._same_evolution_family(set(), {10, 11}))
        mother = dict(unknown, gender=2, serial_num=1)
        father = dict(unknown, gender=1, serial_num=1)
        self.assertIsNone(app.score_breeding_pair(mother, father, ["hp"], None, 30, False, None, False))

    def test_excellent_stats_are_the_highest_three(self):
        pet = {column: 0 for column in app._STAT_COLS.values()}
        pet["hp_talent"] = 1
        pet["adAttack_talent"] = 20
        pet["speed_talent"] = 30
        self.assertEqual(app._get_excellent_stats(pet), ["speed", "adAttack", "hp"])

    def test_big_size_averages_both_parents(self):
        mother = _parent(1, 2, height=120, weight=1500)
        father = _parent(2, 1, height=80, weight=500)
        pair = app.score_breeding_pair(mother, father, [], None, 30, False, None, True)
        expected = (app._get_size_score(mother) + app._get_size_score(father)) / 2
        self.assertAlmostEqual(pair["size_score"], round(expected * 100, 2))


class SyncLockTests(unittest.TestCase):
    def test_worker_releases_the_lock_without_a_client(self):
        progress = app._run_locked("测试锁", lambda queue: queue.put({"done": True, "result": {}}))
        self.assertIsNotNone(progress)
        self.assertTrue(progress.get(timeout=2)["done"])
        released = False
        for _ in range(50):
            if app._sync_lock.acquire(blocking=False):
                app._end_sync()
                released = True
                break
            time.sleep(0.02)
        self.assertTrue(released)


def _parent(serial, gender, height, weight):
    pet = {
        "serial_num": serial,
        "gender": gender,
        "egg_groups": '["植物组"]',
        "evolutionId": "[10]",
        "nature": 1,
        "base_name": "测试",
        "height": height,
        "weight": weight,
        "base_height_low": 80,
        "base_height_high": 120,
        "base_weight_low": 500,
        "base_weight_high": 1500,
    }
    for column in app._STAT_COLS.values():
        pet[column] = 0
    return pet


if __name__ == "__main__":
    unittest.main()
