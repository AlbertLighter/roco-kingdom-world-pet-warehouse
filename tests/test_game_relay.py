import socket
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

    def test_open_s2c_skips_sixteen_byte_prefix(self):
        key = b"0123456789abcdef"
        payload = b"pet-body"
        record = bytearray(10 + len(payload))
        record[0:4] = (0x1346).to_bytes(4, "big")
        record[4:6] = b"\x55\xaa"
        record[10:] = payload
        raw = (b"\x00\x26" + b"\x11" * 14) + bytes(record)
        rem = len(raw) % 16
        trailer_len = 16 - rem if rem <= 10 else 32 - rem
        trailer = b"\x00" * (trailer_len - 6) + b"tsf4g" + bytes([trailer_len])
        encrypted = AES.new(key, AES.MODE_CBC, IV).encrypt(raw + trailer)
        opened = open_s2c(key, encrypted)
        self.assertIsNotNone(opened)
        opcode, body = opened
        self.assertEqual(opcode, 0x1346)
        self.assertEqual(body, payload)


if __name__ == "__main__":
    unittest.main()


class GameRelayKickHelpersTests(unittest.TestCase):
    def test_inet_addr_and_port_dword(self):
        from scripts.game_relay import _inet_addr, _tcp_port_dword

        # 1.2.3.4 -> LSB ??????? MIB_TCPROW ??? Windows ????
        self.assertEqual(_inet_addr("1.2.3.4") & 0xFF, 0x01)
        self.assertEqual((_inet_addr("1.2.3.4") >> 8) & 0xFF, 0x02)
        self.assertEqual(_tcp_port_dword(8195), socket.htons(8195) & 0xFFFF)

    def test_list_game_tcp_filters_by_remote_port(self):
        from unittest.mock import MagicMock, patch
        import psutil
        from scripts import game_relay

        fake_conn_ok = MagicMock()
        fake_conn_ok.laddr = MagicMock(ip="10.0.0.2", port=50000)
        fake_conn_ok.raddr = MagicMock(ip="1.2.3.4", port=8195)
        fake_conn_ok.status = psutil.CONN_ESTABLISHED

        fake_conn_other = MagicMock()
        fake_conn_other.laddr = MagicMock(ip="10.0.0.2", port=50001)
        fake_conn_other.raddr = MagicMock(ip="1.2.3.4", port=443)
        fake_conn_other.status = psutil.CONN_ESTABLISHED

        fake_proc = MagicMock()
        fake_proc.net_connections.return_value = [fake_conn_ok, fake_conn_other]

        with patch.object(game_relay, "_find_pid", return_value=1234), patch("psutil.Process", return_value=fake_proc):
            rows = game_relay.list_game_tcp_to_port("NRC-Win64-Shipping.exe", 8195)
        self.assertEqual(rows, [("10.0.0.2", 50000, "1.2.3.4", 8195)])

    def test_reset_tcp_connections_calls_set_tcp_entry(self):
        from unittest.mock import MagicMock, patch
        from scripts import game_relay

        if __import__("os").name != "nt":
            self.skipTest("SetTcpEntry only on Windows")

        fake_api = MagicMock()
        fake_api.SetTcpEntry.return_value = 0
        with patch("ctypes.windll.iphlpapi", fake_api, create=True):
            ok, errors = game_relay.reset_tcp_connections([("10.0.0.2", 50000, "1.2.3.4", 8195)])
        self.assertEqual(ok, 1)
        self.assertEqual(errors, [])
        self.assertEqual(fake_api.SetTcpEntry.call_count, 1)

