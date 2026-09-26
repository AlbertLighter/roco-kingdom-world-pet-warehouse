import unittest

from scripts.world_teams import find_world_teams


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _msg(field: int, blob: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(blob)) + blob


def _var_field(field: int, value: int) -> bytes:
    return _varint((field << 3) | 0) + _varint(value)


class WorldTeamTests(unittest.TestCase):
    def test_finds_three_teams_of_six(self):
        def pet(gid):
            return _msg(2, _var_field(1, gid))

        def team(gids):
            body = b"".join(pet(gid) for gid in gids)
            return _msg(2, body)

        info = b"".join(team(range(start, start + 6)) for start in (10, 20, 30))
        info += _var_field(4, 1)
        body = _msg(4, _msg(7, info))
        teams = find_world_teams(body)
        self.assertEqual(teams, [list(range(10, 16)), list(range(20, 26)), list(range(30, 36))])


if __name__ == "__main__":
    unittest.main()
