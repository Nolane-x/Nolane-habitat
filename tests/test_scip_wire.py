from __future__ import annotations

import unittest


class ScipWireTests(unittest.TestCase):
    def test_iter_fields_reads_varint_and_length_delimited(self):
        from habitat.semantic.scip_wire import iter_fields

        payload = b"\x08\x96\x01\x12\x03abc"
        self.assertEqual(list(iter_fields(payload)), [(1, 0, 150), (2, 2, b"abc")])

    def test_iter_fields_reads_fixed_width_fields(self):
        from habitat.semantic.scip_wire import iter_fields

        payload = b"\x09\x01\x02\x03\x04\x05\x06\x07\x08\x1d\x09\x0a\x0b\x0c"
        self.assertEqual(
            list(iter_fields(payload)),
            [(1, 1, 0x0807060504030201), (3, 5, 0x0C0B0A09)],
        )

    def test_iter_fields_rejects_truncated_varint(self):
        from habitat.semantic.scip_wire import ScipWireError, iter_fields

        with self.assertRaises(ScipWireError):
            list(iter_fields(b"\x08\x80"))

    def test_iter_fields_rejects_overlong_varint(self):
        from habitat.semantic.scip_wire import ScipWireError, iter_fields

        with self.assertRaises(ScipWireError):
            list(iter_fields(b"\x08" + (b"\x80" * 10) + b"\x00"))

    def test_iter_fields_rejects_truncated_length_delimited_value(self):
        from habitat.semantic.scip_wire import ScipWireError, iter_fields

        with self.assertRaises(ScipWireError):
            list(iter_fields(b"\x12\x05abc"))

    def test_iter_fields_rejects_field_zero(self):
        from habitat.semantic.scip_wire import ScipWireError, iter_fields

        with self.assertRaises(ScipWireError):
            list(iter_fields(b"\x02\x00"))

    def test_iter_fields_rejects_groups(self):
        from habitat.semantic.scip_wire import ScipWireError, iter_fields

        with self.assertRaises(ScipWireError):
            list(iter_fields(b"\x0b"))

    def test_iter_fields_accepts_memoryview(self):
        from habitat.semantic.scip_wire import iter_fields

        self.assertEqual(list(iter_fields(memoryview(b"\x08\x01"))), [(1, 0, 1)])

    def test_decode_packed_int32(self):
        from habitat.semantic.scip_wire import decode_packed_int32

        self.assertEqual(decode_packed_int32(b"\x01\x02\xac\x02"), (1, 2, 300))

    def test_decode_packed_int32_rejects_truncated_value(self):
        from habitat.semantic.scip_wire import ScipWireError, decode_packed_int32

        with self.assertRaises(ScipWireError):
            decode_packed_int32(b"\x80")


if __name__ == "__main__":
    unittest.main()
