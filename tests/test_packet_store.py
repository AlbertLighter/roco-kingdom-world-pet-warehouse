import json
import tempfile
import unittest
from pathlib import Path

import scripts.packet_store as packet_store
from scripts.rocom_capture import Message


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        piece = value & 0x7F
        value >>= 7
        if value:
            out.append(piece | 0x80)
        else:
            out.append(piece)
            return bytes(out)


def _field_varint(field_no: int, value: int) -> bytes:
    return _varint((field_no << 3) | 0) + _varint(value)


def _field_bytes(field_no: int, blob: bytes) -> bytes:
    return _varint((field_no << 3) | 2) + _varint(len(blob)) + blob


class PacketStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self._old = packet_store.DB_PATH
        packet_store.DB_PATH = Path(self.temp.name) / "packets.db"

    def tearDown(self):
        packet_store.DB_PATH = self._old
        self.temp.cleanup()

    def test_parse_and_serialize_pet_page(self):
        name = "小蓝灵".encode("utf-8")
        pet = b"".join([
            _field_varint(1, 42),
            _field_bytes(3, name),
            _field_varint(15, 3005),
            _field_varint(10, 12),
        ])
        body = _field_varint(2, 3) + _field_varint(3, 1) + _field_bytes(4, _field_bytes(1, pet))
        message = Message("s2c", 0x1346, "1.1.1.1:8195|10.0.0.2:1", b"", body)
        message_id = packet_store.record_message(message, source="test")
        listed = packet_store.list_messages()
        self.assertEqual(listed["total"], 1)
        self.assertIn("宠物列表", listed["data"][0]["summary"])

        parsed = packet_store.parse_message(message_id)
        self.assertEqual(parsed["kind"], "pet_list")
        self.assertEqual(parsed["decoded"]["pet_info"]["pet_data"][0]["gid"], 42)

        serialized = packet_store.serialize_message(message_id)
        exported = serialized["export_entry"]
        self.assertEqual(exported["opcode_name"], "ZoneGetPetInfoByPageRsp")
        self.assertEqual(exported["decoded"]["total_page"], 3)
        self.assertIn("小蓝灵", serialized["json"])

    def test_other_opcode_serializes_wire_fields(self):
        body = _field_varint(1, 7) + _field_bytes(2, "abc".encode())
        message = Message("c2s", 0x0102, "sess", b"", body)
        message_id = packet_store.record_message(message, source="test")
        parsed = packet_store.parse_message(message_id)
        self.assertEqual(parsed["kind"], "wire")
        fields = {item["field"]: item for item in parsed["decoded"]["fields"]}
        self.assertEqual(fields[1]["value"], 7)
        self.assertEqual(fields[2]["text"], "abc")
        serialized = packet_store.serialize_message(message_id)
        self.assertEqual(json.loads(serialized["json"])["opcode_name"], "ZoneLoginRsp")


if __name__ == "__main__":
    unittest.main()
