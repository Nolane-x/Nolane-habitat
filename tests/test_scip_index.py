from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tests.scip_fixture import (
    document,
    field_bytes,
    index_payload,
    metadata,
    occurrence,
    sample_index,
    single_line_range,
    symbol_information,
)


class ScipIndexParserTests(unittest.TestCase):
    def _write(self, payload: bytes, name: str = "index.scip") -> Path:
        path = Path(self.tempdir.name) / name
        path.write_bytes(payload)
        return path

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_parses_tool_identity_documents_definitions_references_and_diagnostics(self):
        from habitat.semantic.scip_index import parse_scip_index

        payload, symbol = sample_index()
        snapshot = parse_scip_index(self._write(payload))

        self.assertEqual(snapshot.index_digest, hashlib.sha256(payload).hexdigest())
        self.assertEqual(snapshot.project_root, "file:///workspace")
        self.assertEqual(snapshot.protocol_version, 0)
        self.assertEqual(snapshot.text_document_encoding, 1)
        self.assertEqual(snapshot.tool.name, "scip-python")
        self.assertEqual(snapshot.tool.version, "0.6.0")
        self.assertEqual(snapshot.tool.arguments, ("index",))
        self.assertEqual(tuple(doc.path for doc in snapshot.documents), ("src/a.py", "src/b.py"))

        definitions = snapshot.definitions_by_symbol[symbol]
        references = snapshot.references_by_symbol[symbol]
        self.assertEqual(len(definitions), 1)
        self.assertEqual(len(references), 1)
        self.assertEqual(
            (definitions[0].path, definitions[0].start_line, definitions[0].start_column, definitions[0].end_line, definitions[0].end_column),
            ("src/a.py", 1, 5, 1, 8),
        )
        self.assertEqual(
            (references[0].path, references[0].start_line, references[0].start_column),
            ("src/b.py", 3, 9),
        )
        self.assertEqual(len(snapshot.documents[1].diagnostics), 1)
        diagnostic = snapshot.documents[1].diagnostics[0]
        self.assertEqual((diagnostic.severity, diagnostic.code, diagnostic.message, diagnostic.source), ("warning", "W1", "fixture warning", "fixture"))
        self.assertEqual((diagnostic.location.start_line, diagnostic.location.start_column), (3, 9))
        self.assertEqual(snapshot.documents[0].symbols[0].display_name, "foo")
        self.assertEqual(snapshot.documents[0].symbols[0].documentation, ("Demo function",))

    def test_typed_range_takes_precedence_over_legacy_range(self):
        from habitat.semantic.scip_index import parse_scip_index

        symbol = "scip-python python demo 1.0 foo()."
        item = occurrence(symbol, roles=1, legacy_range=(9, 1, 2), typed_single=(1, 3, 6))
        payload = index_payload(metadata_payload=metadata(), documents=(document("a.py", occurrences=(item,)),))
        snapshot = parse_scip_index(self._write(payload))
        location = snapshot.definitions_by_symbol[symbol][0]
        self.assertEqual((location.start_line, location.start_column, location.end_line, location.end_column), (2, 4, 2, 7))

    def test_rejects_noncanonical_document_paths(self):
        from habitat.semantic.scip_index import ScipParseError, parse_scip_index

        invalid = ("/a.py", "a/../b.py", "a/./b.py", "a//b.py", "a\\b.py", "a\x00b.py", "")
        for relative_path in invalid:
            with self.subTest(relative_path=relative_path):
                payload = index_payload(metadata_payload=metadata(), documents=(document(relative_path),))
                with self.assertRaises(ScipParseError):
                    parse_scip_index(self._write(payload, "bad.scip"))

    def test_rejects_duplicate_metadata(self):
        from habitat.semantic.scip_index import ScipParseError, parse_scip_index

        meta = metadata()
        payload = field_bytes(1, meta) + field_bytes(1, meta)
        with self.assertRaises(ScipParseError):
            parse_scip_index(self._write(payload))

    def test_rejects_oversized_input_before_parse(self):
        from habitat.semantic.scip_index import ScipParseError, parse_scip_index

        payload, _ = sample_index()
        with self.assertRaises(ScipParseError):
            parse_scip_index(self._write(payload), max_index_bytes=len(payload) - 1)

    def test_rejects_document_and_occurrence_limits(self):
        from habitat.semantic.scip_index import ScipParseError, parse_scip_index

        two_docs = index_payload(metadata_payload=metadata(), documents=(document("a.py"), document("b.py")))
        with self.assertRaises(ScipParseError):
            parse_scip_index(self._write(two_docs), max_documents=1)

        one = occurrence("local 1", typed_single=(0, 0, 1))
        two = occurrence("local 2", typed_single=(0, 2, 3))
        payload = index_payload(metadata_payload=metadata(), documents=(document("a.py", occurrences=(one, two)),))
        with self.assertRaises(ScipParseError):
            parse_scip_index(self._write(payload), max_occurrences=1)

    def test_rejects_malformed_ranges(self):
        from habitat.semantic.scip_index import ScipParseError, parse_scip_index

        bad_legacy = occurrence("local 1", roles=1, legacy_range=(0, 1))
        payload = index_payload(metadata_payload=metadata(), documents=(document("a.py", occurrences=(bad_legacy,)),))
        with self.assertRaises(ScipParseError):
            parse_scip_index(self._write(payload))

        bad_typed_payload = field_bytes(8, single_line_range(0, 4, 3))
        raw_occurrence = field_bytes(2, b"local 1") + bad_typed_payload
        payload = index_payload(metadata_payload=metadata(), documents=(document("a.py", occurrences=(raw_occurrence,)),))
        with self.assertRaises(ScipParseError):
            parse_scip_index(self._write(payload))

    def test_empty_symbol_occurrence_can_carry_diagnostic_but_is_not_indexed(self):
        from habitat.semantic.scip_index import parse_scip_index
        from tests.scip_fixture import diagnostic

        item = occurrence("", typed_single=(0, 0, 1), diagnostics=(diagnostic("orphan"),))
        payload = index_payload(metadata_payload=metadata(), documents=(document("a.py", occurrences=(item,)),))
        snapshot = parse_scip_index(self._write(payload))
        self.assertEqual(snapshot.definitions_by_symbol, {})
        self.assertEqual(snapshot.references_by_symbol, {})
        self.assertEqual(snapshot.documents[0].diagnostics[0].message, "orphan")

    def test_symbol_information_preserves_identity_and_kind(self):
        from habitat.semantic.scip_index import parse_scip_index

        symbol = "scip-python python demo 1.0 Foo#"
        info = symbol_information(symbol, display_name="Foo", kind=7, documentation=("Class docs",), enclosing_symbol="local 9")
        payload = index_payload(metadata_payload=metadata(), documents=(document("a.py", symbols=(info,)),))
        snapshot = parse_scip_index(self._write(payload))
        parsed = snapshot.documents[0].symbols[0]
        self.assertEqual((parsed.symbol, parsed.display_name, parsed.kind, parsed.documentation, parsed.enclosing_symbol), (symbol, "Foo", 7, ("Class docs",), "local 9"))


if __name__ == "__main__":
    unittest.main()
