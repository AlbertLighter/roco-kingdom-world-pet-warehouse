import unittest

from Crypto.Cipher import AES

from scripts.game_relay import IV, ack_key, open_s2c, pop_packet


def _gcp(command: int, extra: bytes, body: bytes) -> bytes:
    head = bytearray(21)
    head[0:2] = b"\x33\x66"
    head[6:8] = command.to_bytes(2, "big")
    head_len = 21 + len(extra)
    head[13:17] = head_len.to_bytes(4, "big")
    head[17:21] = len(body).to_bytes(4, "big")
    return bytes(head) + extra + body


class GameRelayParseTests(unittest.TestCase):
    def test_pop_packet_splits_a_stream(self):
        first = _gcp(0x1001, b"\x00\x00", b"")
        second = _gcp(0x1002, b"\x00" * 18, b"")
        buf = bytearray(b"\x99" + first + second + b"\x33")
        self.assertEqual(pop_packet(buf), first)
        self.assertEqual(pop_packet(buf), second)
        self.assertIsNone(pop_packet(buf))
        self.assertEqual(bytes(buf), b"\x33")

    def test_ack_key_is_at_the_mitm_offset(self):
        key = b"0123456789abcdef"
        pkt = _gcp(0x1002, b"\xab\xcd" + key, b"")
        self.assertEqual(ack_key(pkt), key)
        self.assertIsNone(ack_key(_gcp(0x4013, b"\xab\xcd" + key, b"")))

    def test_open_s2c_uses_fixed_iv_and_internal_header(self):
        key = b"0123456789abcdef"
        header = bytearray(30)
        header[4:6] = b"\x55\xaa"
        header[16:20] = (0x1346).to_bytes(4, "big")
        payload = b"pet-body"
        raw = bytes(header) + payload
        rem = len(raw) % 16
        trailer_len = 16 - rem if rem <= 10 else 32 - rem
        trailer = b"\x00" * (trailer_len - 6) + b"tsf4g" + bytes([trailer_len])
        plain = raw + trailer
        encrypted = AES.new(key, AES.MODE_CBC, IV).encrypt(plain)
        opened = open_s2c(key, encrypted)
        self.assertIsNotNone(opened)
        opcode, body = opened
        self.assertEqual(opcode, 0x1346)
        self.assertEqual(body, payload)


if __name__ == "__main__":
    unittest.main()
