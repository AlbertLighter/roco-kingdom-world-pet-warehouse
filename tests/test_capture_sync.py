import json
import tempfile
import unittest
from pathlib import Path

from scripts.capture_sync import (
    PetPageCollector,
    decode_pet_name,
    empty_capture_reason,
    pet_record,
    sync_from_export,
    upsert_pets,
)
from scripts.rocom_capture import Engine
from scripts.fetcher import init_db
import scripts.fetcher as fetcher


def sample_pet(**overrides):
    pet = {
        "gid": 42,
        "base_conf_id": 3005,
        "conf_id": 2000671,
        "name": "e5b08fe8939de781b5",
        "level": 60,
        "nature": 11,
        "gender": 2,
        "talent_rank": 4,
        "height": 116,
        "weight": 78900,
        "blood_id": 19,
        "mutation_type": 0,
        "ball_id": 100002,
        "speciality_id": 7,
        "skill_dam_type": [5],
        "attribute_info": {
            "hp": {"base_value": 310, "total_race": 125, "talent": 32},
            "attack": {"base_value": 80, "total_race": 40, "talent": 1},
            "special_attack": {"base_value": 70, "total_race": 30, "talent": 2},
            "defense": {"base_value": 60, "total_race": 20, "talent": 3},
            "special_defense": {"base_value": 50, "total_race": 10, "talent": 4},
            "speed": {"base_value": 40, "total_race": 9, "talent": 5},
        },
        "skill": {
            "skill_data": [
                {"id": 111, "pos": 2, "is_equipped": True},
                {"id": 222, "pos": 1, "is_equipped": True},
                {"id": 333, "pos": 3, "is_equipped": False},
            ]
        },
    }
    pet.update(overrides)
    return pet


class CaptureSyncTests(unittest.TestCase):
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

    def test_empty_capture_reason_names_the_gap(self):
        engine = Engine()
        engine.tcp_segments = 4
        engine.no_key = 4
        text = empty_capture_reason(engine)
        self.assertIn("0x1002", text)
        self.assertIn("TCP段 4", text)

    def test_decode_name_and_record(self):
        self.assertEqual(decode_pet_name("e5b08fe8939de781b5"), "小蓝灵")
        record = pet_record(sample_pet())
        self.assertEqual(record["serial_num"], 42)
        self.assertEqual(record["base_id"], 3005)
        self.assertEqual(record["name"], "小蓝灵")
        self.assertEqual(record["hp"], 310)
        self.assertEqual(record["hp_race"], 125)
        self.assertEqual(record["hp_talent"], 32)
        self.assertEqual(record["equip_skill_1"], 222)
        self.assertEqual(record["equip_skill_2"], 111)
        self.assertEqual(record["talent_skill"], 7)
        self.assertEqual(json.loads(record["skill_dam_type"]), [5])

    def test_export_upsert_marks_missing_only_when_pages_complete(self):
        upsert_pets([pet_record(sample_pet(gid=7, name="旧"))], db_path=self.db_path, mark_missing=False)
        export = Path(self.temp_dir.name) / "partial.json"
        export.write_text(json.dumps([
            {
                "opcode_name": "ZoneGetPetInfoByPageRsp",
                "decoded": {"total_page": 2, "req_page": 1, "pet_info": {"pet_data": [sample_pet()]}},
            }
        ]), encoding="utf-8")
        result = sync_from_export(str(export), db_path=self.db_path)
        self.assertEqual(result["total"], 1)
        self.assertFalse(result["complete"])
        self.assertEqual(result["released"], 0)

        export.write_text(json.dumps([
            {
                "opcode_name": "ZoneGetPetInfoByPageRsp",
                "decoded": {"total_page": 1, "req_page": 1, "version": 3, "pet_info": {"pet_data": [sample_pet()]}},
            }
        ]), encoding="utf-8")
        result = sync_from_export(str(export), db_path=self.db_path)
        self.assertFalse(result["complete"])
        self.assertEqual(result["released"], 0)
        released = upsert_pets([pet_record(sample_pet())], db_path=self.db_path, mark_missing=True)
        self.assertEqual(released["released"], 1)

    def test_version_change_drops_previous_pages(self):
        collector = PetPageCollector()
        collector.add_decoded({"version": 1, "total_page": 2, "req_page": 1, "pet_info": {"pet_data": [sample_pet(gid=1)]}})
        collector.add_decoded({"version": 2, "total_page": 1, "req_page": 1, "pet_info": {"pet_data": [sample_pet(gid=2)]}})
        records, complete = collector.snapshot()
        self.assertTrue(complete)
        self.assertEqual([row["serial_num"] for row in records], [2])


if __name__ == "__main__":
    unittest.main()
