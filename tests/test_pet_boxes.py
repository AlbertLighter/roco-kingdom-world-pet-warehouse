import unittest

from scripts.pet_boxes import find_boxes, freed_gids
from scripts.world_teams import _read_varint


def _tag(field: int, wire: int) -> bytes:
    value = (field << 3) | wire
    return _read_varint and bytes([value])


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


class PetBoxTests(unittest.TestCase):
    def test_box_order_and_free_response(self):
        gids = list(range(100, 130))
        body = _varint((1 << 3) | 0) + _varint(3)
        body += b"".join(_varint((3 << 3) | 0) + _varint(gid) for gid in gids)
        packet = _msg(9, body)
        boxes = find_boxes(packet)
        self.assertEqual(boxes[3], gids)
        freed = _varint((2 << 3) | 0) + _varint(100) + _varint((2 << 3) | 0) + _varint(101)
        self.assertEqual(freed_gids(freed), [100, 101])


if __name__ == "__main__":
    unittest.main()
