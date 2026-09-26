"""tsf4g/GCP 分帧、会话密钥和 0x4013 解密。

字节布局与 rocom-parse 的 gcp 包一致：定长 21 字节头，magic 0x3366，
0x1002 的扩展头里明文带 16 字节 AES 密钥，0x4013 用 AES-CBC 解密。
"""

from __future__ import annotations

from Crypto.Cipher import AES

FIXED_HDR_LEN = 21
KEY_OFFSET = 2
KEY_LEN = 16
MAGIC = b"\x33\x66"
FIXED_AES_IV = b"\x00" * 16
IVDECODER_AES_IV = bytes(range(16))
S2C_MARKER = b"\x55\xaa"
S2C_BODY_OFFSET = 10
S2C_OPCODE_OFFSET = 2
C2S_OPCODE_OFFSET = 6
S2C_MARKER_OFFSET = 4

CMD_ACK = 0x1002
CMD_DATA = 0x4013

C2S = "c2s"
S2C = "s2c"


class Packet:
    def __init__(self, command: int, sequence: int, header_extra: bytes, body: bytes) -> None:
        self.command = command
        self.sequence = sequence
        self.header_extra = header_extra
        self.body = body


def _index_magic(buf: bytes, start: int) -> int:
    limit = len(buf) - 1
    for index in range(start, limit):
        if buf[index] == MAGIC[0] and buf[index + 1] == MAGIC[1]:
            return index
    return -1


def deframe(buf: bytes) -> tuple[list[Packet], bytes]:
    """从字节流里切出完整 GCP 包，剩下的字节等下一段 TCP 数据。"""
    packets: list[Packet] = []
    offset = 0
    size = len(buf)
    while offset + FIXED_HDR_LEN <= size:
        if buf[offset] != MAGIC[0] or buf[offset + 1] != MAGIC[1]:
            nxt = _index_magic(buf, offset + 1)
            if nxt < 0:
                return packets, b""
            offset = nxt
            continue
        command = int.from_bytes(buf[offset + 6 : offset + 8], "big")
        sequence = int.from_bytes(buf[offset + 9 : offset + 13], "big")
        hdr_len = int.from_bytes(buf[offset + 13 : offset + 17], "big")
        body_len = int.from_bytes(buf[offset + 17 : offset + 21], "big")
        if hdr_len < FIXED_HDR_LEN or hdr_len + body_len > 8 * 1024 * 1024:
            offset += 2
            continue
        total = hdr_len + body_len
        if offset + total > size:
            break
        extra = bytes(buf[offset + FIXED_HDR_LEN : offset + hdr_len])
        body = bytes(buf[offset + hdr_len : offset + total])
        packets.append(Packet(command, sequence, extra, body))
        offset += total
    return packets, bytes(buf[offset:])


def extract_key(header_extra: bytes) -> bytes | None:
    end = KEY_OFFSET + KEY_LEN
    if len(header_extra) < end:
        return None
    return bytes(header_extra[KEY_OFFSET:end])


def _cbc(key: bytes, iv: bytes, body: bytes) -> bytes:
    return AES.new(key, AES.MODE_CBC, iv).decrypt(body)


def decrypt_data(key: bytes, body: bytes) -> bytes | None:
    """AES-CBC。长度允许时用包内 IV，否则用全零 IV。不剥填充。"""
    if len(key) != KEY_LEN:
        return None
    if len(body) >= 32 and (len(body) - 16) % 16 == 0:
        return _cbc(key, body[:16], body[16:])
    if len(body) >= 16 and len(body) % 16 == 0:
        return _cbc(key, FIXED_AES_IV, body)
    return None


def decrypt_matching(key: bytes, body: bytes, direction: str) -> bytes | None:
    """依次试包内 IV、RKPP 固定 IV、全零 IV。RKPP 的明文从偏移 16 才是应用层。"""
    if len(key) != KEY_LEN or len(body) < 16 or len(body) % 16 != 0:
        return None
    candidates: list[bytes] = []
    if len(body) >= 32:
        candidates.append(_cbc(key, body[:16], body[16:]))
    full = _cbc(key, IVDECODER_AES_IV, body)
    if len(full) > 16:
        candidates.append(full[16:])
    candidates.append(full)
    candidates.append(_cbc(key, FIXED_AES_IV, body))
    for plain in candidates:
        if valid_plain(direction, plain):
            return plain
    return None


def valid_plain(direction: str, plain: bytes) -> bool:
    if direction != S2C:
        return True
    end = S2C_MARKER_OFFSET + 2
    return len(plain) >= end and plain[S2C_MARKER_OFFSET:end] == S2C_MARKER


def app_opcode(direction: str, plain: bytes) -> int | None:
    offset = S2C_OPCODE_OFFSET if direction == S2C else C2S_OPCODE_OFFSET
    if len(plain) < offset + 2:
        return None
    return int.from_bytes(plain[offset : offset + 2], "big")


def app_body(direction: str, plain: bytes) -> bytes:
    if direction == S2C:
        if len(plain) >= S2C_BODY_OFFSET:
            return plain[S2C_BODY_OFFSET:]
        return b""
    if len(plain) >= 8:
        return plain[8:]
    return b""
