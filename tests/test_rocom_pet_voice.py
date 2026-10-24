# -*- coding: utf-8 -*-
import unittest

from scripts.rocom_pet import _pet, scan_fields


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _tag(field_no: int, wire: int = 0) -> bytes:
    return _varint((field_no << 3) | wire)


class PetVoiceFieldTests(unittest.TestCase):
    def test_pet_parses_field_93_as_voice(self):
        # minimal PetData: gid=7, voice=53 (field 93)
        blob = _tag(1) + _varint(7) + _tag(93) + _varint(53)
        pet = _pet(blob)
        self.assertEqual(pet.get("gid"), 7)
        self.assertEqual(pet.get("voice"), 53)

    def test_pet_parses_negative_voice_uint64(self):
        # -36 as uint64 varint
        neg = (1 << 64) - 36
        blob = _tag(1) + _varint(9) + _tag(93) + _varint(neg)
        pet = _pet(blob)
        self.assertEqual(pet.get("voice"), neg)


if __name__ == "__main__":
    unittest.main()
