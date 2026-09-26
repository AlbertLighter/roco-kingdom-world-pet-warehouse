import json
import unittest
from pathlib import Path

from Crypto.Cipher import AES

from scripts.rocom_capture import Engine, FileKeyStore
from scripts.rocom_gcp import IVDECODER_AES_IV, decrypt_data, decrypt_matching, deframe, extract_key, valid_plain
from scripts.rocom_pet import parse_pet_list


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


def _gcp(command: int, sequence: int, extra: bytes, body: bytes) -> bytes:
    hdr_len = 21 + len(extra)
    head = bytearray(21)
    head[0:2] = b"\x33\x66"
    head[2:4] = (0x000B).to_bytes(2, "big")
    head[4:6] = (0x000B).to_bytes(2, "big")
    head[6:8] = command.to_bytes(2, "big")
    head[9:13] = sequence.to_bytes(4, "big")
    head[13:17] = hdr_len.to_bytes(4, "big")
    head[17:21] = len(body).to_bytes(4, "big")
    return bytes(head) + extra + body


def _page_body() -> bytes:
    name = "小蓝灵".encode("utf-8")
    attr = _field_varint(1, 125) + _field_varint(2, 32) + _field_varint(3, 310)
    attrs = _field_bytes(1, attr)
    skill = _field_varint(1, 222) + _field_varint(4, 1) + _field_varint(5, 1)
    skills = _field_bytes(1, skill)
    pet = b"".join([
        _field_varint(1, 42),
        _field_varint(2, 2000671),
        _field_bytes(3, name),
        _field_bytes(6, _varint(5)),
        _field_varint(7, 11),
        _field_varint(8, 2),
        _field_varint(10, 60),
        _field_varint(11, 100002),
        _field_bytes(12, skills),
        _field_bytes(14, attrs),
        _field_varint(15, 3005),
        _field_varint(26, 116),
        _field_varint(27, 78900),
        _field_varint(45, 0),
        _field_varint(47, 19),
        _field_varint(55, 4),
        _field_varint(82, 7),
    ])
    pet_list = _field_bytes(1, pet)
    return b"".join([
        _field_varint(2, 1),
        _field_varint(3, 1),
        _field_bytes(4, pet_list),
        _field_varint(6, 9),
    ])


class RocomPortTests(unittest.TestCase):
    def test_deframe_skips_noise_and_keeps_incomplete_tail(self):
        extra = b"\x00\x01" + b"k" * 16
        packet = _gcp(0x1002, 3, extra, b"")
        packets, rest = deframe(b"\x00\x11" + packet + b"\x33")
        self.assertEqual(len(packets), 1)
        self.assertEqual(extract_key(packets[0].header_extra), b"k" * 16)
        self.assertEqual(rest, b"\x33")

    def test_decrypt_embedded_iv_and_marker(self):
        key = b"0123456789abcdef"
        plain = bytearray(32)
        plain[2:4] = (0x1346).to_bytes(2, "big")
        plain[4:6] = b"\x55\xaa"
        iv = b"iviviviviviviviv"
        body = iv + AES.new(key, AES.MODE_CBC, iv).encrypt(bytes(plain))
        out = decrypt_data(key, body)
        self.assertTrue(valid_plain("s2c", out))
        self.assertEqual(out[2:6], b"\x13\x46\x55\xaa")

    def test_split_tcp_yields_pet_page(self):
        key = bytes(range(16))
        body = _page_body()
        plain = bytearray(10 + len(body) + 16)
        plain[2:4] = (0x1346).to_bytes(2, "big")
        plain[4:6] = b"\x55\xaa"
        plain[10:10 + len(body)] = body
        pad = (-len(plain)) % 16
        plain.extend(b"\x00" * pad)
        iv = b"0123456789abcdef"
        encrypted = iv + AES.new(key, AES.MODE_CBC, iv).encrypt(bytes(plain))
        ack = _gcp(0x1002, 1, b"\x00\x00" + key, b"")
        data = _gcp(0x4013, 2, b"", encrypted)
        blob = ack + data
        seen = []
        engine = Engine(on_message=seen.append)
        engine.feed_segment("1.2.3.4", 8195, "10.0.0.8", 40000, 5000, blob[:40])
        engine.feed_segment("1.2.3.4", 8195, "10.0.0.8", 40000, 5040, blob[40:])
        self.assertEqual(len(seen), 1)
        decoded = parse_pet_list(seen[0].app_body)
        pet = decoded["pet_info"]["pet_data"][0]
        self.assertEqual(decoded["total_page"], 1)
        self.assertEqual(decoded["version"], 9)
        self.assertEqual(pet["gid"], 42)
        self.assertEqual(pet["base_conf_id"], 3005)
        self.assertEqual(pet["name"], "小蓝灵")
        self.assertEqual(pet["attribute_info"]["hp"]["base_value"], 310)
        self.assertEqual(pet["skill"]["skill_data"][0]["id"], 222)
        self.assertEqual(pet["skill_dam_type"], [5])

    def test_data_before_key_is_counted(self):
        engine = Engine()
        data = _gcp(0x4013, 1, b"", b"\x00" * 32)
        engine.feed_segment("10.0.0.8", 40000, "1.2.3.4", 8195, 1, data)
        self.assertEqual(engine.tcp_segments, 1)
        self.assertEqual(engine.no_key, 1)
        self.assertEqual(engine.key_frames, 0)
        self.assertIn("1.2.3.4:8195", engine.summary())
        self.assertIn("0x1002", engine.failure_hint())

    def test_latest_key_applies_to_a_new_connection(self):
        import tempfile

        key = b"0123456789abcdef"
        plain = bytearray(32)
        plain[2:4] = (0x1346).to_bytes(2, "big")
        plain[4:6] = b"\x55\xaa"
        blob = (b"\x11" * 16) + bytes(plain)
        blob += b"\x00" * ((-len(blob)) % 16)
        encrypted = AES.new(key, AES.MODE_CBC, IVDECODER_AES_IV).encrypt(blob)
        self.assertEqual(decrypt_matching(key, encrypted, "s2c"), bytes(plain))

        with tempfile.TemporaryDirectory() as temp:
            store = FileKeyStore(Path(temp))
            first = Engine(keys=store)
            ack = _gcp(0x1002, 1, b"\xab\xcd" + key, b"")
            first.feed_segment("10.0.0.8", 40000, "1.2.3.4", 8195, 1, ack)
            seen = []
            second = Engine(keys=store, on_message=seen.append)
            data = _gcp(0x4013, 2, b"", encrypted)
            second.feed_segment("1.2.3.4", 8195, "10.0.0.9", 40001, 10, data)
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0].opcode, 0x1346)
            self.assertTrue(store.latest_path().is_file())

    def test_late_ack_still_yields_key(self):
        key = bytes(range(16))
        ack = _gcp(0x1002, 1, b"\x00\x00" + key, b"")
        engine = Engine()
        engine.feed_segment("1.2.3.4", 8195, "10.0.0.8", 40000, 5000, b"\x33\x66" + b"\x00" * 40)
        engine.feed_segment("1.2.3.4", 8195, "10.0.0.8", 40000, 1000, ack)
        self.assertEqual(engine.key_frames, 1)
        flow = next(iter(engine.flows.values()))
        self.assertEqual(flow.session.key, key)

    def test_cached_key_survives_restart(self):
        import tempfile

        key = bytes(range(16))
        with tempfile.TemporaryDirectory() as temp:
            store = FileKeyStore(Path(temp))
            first = Engine(keys=store)
            ack = _gcp(0x1002, 1, b"\xab\xcd" + key, b"")
            first.feed_segment("10.0.0.8", 40000, "1.2.3.4", 8195, 1, ack)
            second = Engine(keys=store)
            self.assertEqual(len(second.flows), 0)
            second.feed_segment("1.2.3.4", 8195, "10.0.0.8", 40000, 1, b"")
            flow = next(iter(second.flows.values()))
            self.assertEqual(flow.session.key, key)
            self.assertTrue(flow.session.from_cache)

    def test_real_export_payload_if_present(self):
        path = Path(__file__).resolve().parents[1] / "data" / "rkms_export_20260702T124036.json"
        if not path.is_file():
            self.skipTest("没有现成导出")
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        entry = next(item for item in data if item.get("opcode_name") == "ZoneGetPetInfoByPageRsp")
        decoded = parse_pet_list(bytes.fromhex(entry["payload_hex"]))
        pets = decoded["pet_info"]["pet_data"]
        self.assertEqual(decoded["total_page"], 24)
        self.assertEqual(decoded["req_page"], 1)
        self.assertGreaterEqual(len(pets), 40)
        self.assertEqual(pets[0]["gid"], 1)
        self.assertEqual(pets[0]["base_conf_id"], 3005)
        self.assertEqual(pets[0]["name"], "小蓝灵")
        self.assertEqual(pets[0]["attribute_info"]["hp"]["base_value"], 310)


if __name__ == "__main__":
    unittest.main()
