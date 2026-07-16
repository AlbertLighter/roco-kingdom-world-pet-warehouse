import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.main import match_and_fill_gender_by_stats


STATS = {
    "hp": 101,
    "adAttack": 52,
    "adDefense": 63,
    "apAttack": 74,
    "apDefense": 85,
    "speed": 96,
}


class OcrGenderSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "warehouse.db")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE pet_instances (
                    serial_num INTEGER PRIMARY KEY,
                    name TEXT,
                    hp INTEGER,
                    adAttack INTEGER,
                    adDefense INTEGER,
                    apAttack INTEGER,
                    apDefense INTEGER,
                    speed INTEGER,
                    is_active INTEGER,
                    gender INTEGER
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def insert_pet(self, serial_num, *, gender=0, active=1, **stats):
        values = {**STATS, **stats}
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                INSERT INTO pet_instances (
                    serial_num, name, hp, adAttack, adDefense,
                    apAttack, apDefense, speed, is_active, gender
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                serial_num,
                f"pet-{serial_num}",
                values["hp"],
                values["adAttack"],
                values["adDefense"],
                values["apAttack"],
                values["apDefense"],
                values["speed"],
                active,
                gender,
            ))
            conn.commit()
        finally:
            conn.close()

    def request(self, gender=1, **stats):
        return match_and_fill_gender_by_stats(
            {**STATS, **stats, "gender": gender},
            db_path=self.db_path,
        )

    def stored_gender(self, serial_num):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                "SELECT gender FROM pet_instances WHERE serial_num = ?",
                (serial_num,),
            ).fetchone()[0]
        finally:
            conn.close()

    def test_unique_exact_match_fills_unknown_gender(self):
        self.insert_pet(11)
        result = self.request(gender=2)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["serial_num"], 11)
        self.assertEqual(self.stored_gender(11), 2)

    def test_all_six_stats_must_match(self):
        self.insert_pet(11, speed=95)
        result = self.request()
        self.assertEqual(result["status"], "no_match")
        self.assertEqual(self.stored_gender(11), 0)

    def test_duplicate_stats_are_ambiguous_even_if_one_gender_is_already_set(self):
        self.insert_pet(11, gender=0)
        self.insert_pet(12, gender=2)
        result = self.request()
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["match_count"], 2)
        self.assertEqual(self.stored_gender(11), 0)

    def test_existing_gender_is_never_overwritten(self):
        self.insert_pet(11, gender=2)
        result = self.request(gender=1)
        self.assertEqual(result["status"], "already_set")
        self.assertEqual(self.stored_gender(11), 2)

    def test_null_gender_is_treated_as_unknown(self):
        self.insert_pet(11, gender=None)
        result = self.request(gender=1)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(self.stored_gender(11), 1)

    def test_inactive_pet_does_not_participate(self):
        self.insert_pet(11, active=0)
        self.insert_pet(12, active=1)
        result = self.request(gender=1)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["serial_num"], 12)
        self.assertEqual(self.stored_gender(11), 0)
        self.assertEqual(self.stored_gender(12), 1)


if __name__ == "__main__":
    unittest.main()
