import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.pet_boxes import apply_box_moves, apply_boxes, find_box_moves, find_boxes, freed_gids
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
        partial = _varint((1 << 3) | 0) + _varint(4)
        partial += b"".join(_varint((3 << 3) | 0) + _varint(gid) for gid in (100, 101))
        partial += b"".join(_varint((3 << 3) | 0) + _varint(0) for _ in range(28))
        self.assertEqual(find_boxes(_msg(9, partial))[4][:4], [100, 101, 0, 0])
        freed = _varint((2 << 3) | 0) + _varint(100) + _varint((2 << 3) | 0) + _varint(101)
        self.assertEqual(freed_gids(freed), [100, 101])

    def test_partial_snapshot_keeps_boxes_it_did_not_see(self):
        directory, path = _warehouse(range(1001, 1041), placed=[(1040, 8, 0), (1005, 1, 4)])
        self.addCleanup(directory.cleanup)
        packet = _boxes(
            (1, list(range(1001, 1011))),
            (2, list(range(1011, 1021))),
            (3, list(range(1021, 1031))),
            (4, [1031, 1032]),
        )
        result = apply_boxes(packet, db_path=path)
        self.assertEqual(result["boxes"], 4)
        conn = sqlite3.connect(path)
        self.assertEqual(_at(conn, 1001), (1, 0))
        self.assertEqual(_at(conn, 1005), (1, 4))
        self.assertEqual(_at(conn, 1031), (4, 0))
        self.assertEqual(_at(conn, 1040), (8, 0))
        conn.close()

    def test_too_few_boxes_does_not_clear_positions(self):
        directory, path = _warehouse(range(1001, 1021), placed=[(1001, 9, 2)])
        self.addCleanup(directory.cleanup)
        result = apply_boxes(_boxes((1, list(range(1001, 1011)))), db_path=path)
        self.assertEqual(result["boxes"], 0)
        conn = sqlite3.connect(path)
        self.assertEqual(_at(conn, 1001), (9, 2))
        conn.close()

    def test_swap_updates_only_the_moved_pets(self):
        directory, path = _warehouse([1001, 1002, 1003], placed=[(1001, 1, 0), (1002, 1, 1), (1003, 6, 3)])
        self.addCleanup(directory.cleanup)
        packet = _move(1001, 1, 2) + _move(1002, 1, 1)
        result = apply_box_moves(packet, db_path=path)
        self.assertEqual(result["updated"], 2)
        conn = sqlite3.connect(path)
        self.assertEqual(_at(conn, 1001), (1, 1))
        self.assertEqual(_at(conn, 1002), (1, 0))
        self.assertEqual(_at(conn, 1003), (6, 3))
        conn.close()

    def test_pet_body_is_not_a_box_move(self):
        name = "小蓝灵".encode()
        pet = _varint((1 << 3) | 0) + _varint(1001)
        pet += _varint((2 << 3) | 0) + _varint(2000671)
        pet += _msg(3, name)
        pet += _varint((10 << 3) | 0) + _varint(12)
        self.assertEqual(find_box_moves(pet), [])


def _warehouse(serials, placed=()):
    directory = tempfile.TemporaryDirectory()
    path = str(Path(directory.name) / "warehouse.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE pet_instances (
            serial_num INTEGER PRIMARY KEY,
            is_active INTEGER DEFAULT 1,
            box_id INTEGER,
            box_slot INTEGER
        )
        """
    )
    conn.executemany("INSERT INTO pet_instances (serial_num) VALUES (?)", [(number,) for number in serials])
    for serial, box_id, slot in placed:
        conn.execute(
            "UPDATE pet_instances SET box_id = ?, box_slot = ? WHERE serial_num = ?",
            (box_id, slot, serial),
        )
    conn.commit()
    conn.close()
    return directory, path


def _boxes(*boxes):
    chunks = []
    for box_id, gids in boxes:
        body = _varint((1 << 3) | 0) + _varint(box_id)
        body += b"".join(_varint((3 << 3) | 0) + _varint(gid) for gid in gids)
        chunks.append(_msg(9, body))
    return b"".join(chunks)


def _move(gid, box_id, pos):
    body = _varint((1 << 3) | 0) + _varint(gid)
    body += _varint((2 << 3) | 0) + _varint(0)
    body += _varint((3 << 3) | 0) + _varint(box_id)
    body += _varint((4 << 3) | 0) + _varint(pos)
    return _msg(18, body)


def _at(conn, serial):
    return conn.execute("SELECT box_id, box_slot FROM pet_instances WHERE serial_num = ?", (serial,)).fetchone()


if __name__ == "__main__":
    unittest.main()
