from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tests.scip_fixture import sample_index


class ScipProviderTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.index_path = self.root / "index.scip"
        payload, self.symbol = sample_index()
        self.index_path.write_bytes(payload)
        (self.root / "src").mkdir()
        (self.root / "src" / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
        (self.root / "src" / "b.py").write_text("x = 1\n\nvalue = foo()\n", encoding="utf-8")

    def tearDown(self):
        self.tempdir.cleanup()

    def _provider(self):
        from habitat.semantic.scip_index import parse_scip_index
        from habitat.semantic.scip_provider import ScipSemanticProvider

        snapshot = parse_scip_index(self.index_path)
        digests = {
            "src/a.py": hashlib.sha256((self.root / "src" / "a.py").read_bytes()).hexdigest(),
            "src/b.py": hashlib.sha256((self.root / "src" / "b.py").read_bytes()).hexdigest(),
        }
        return ScipSemanticProvider(
            snapshot,
            provider_id="scip.fixture",
            activation_revision="rev-1",
            source_digests=digests,
        )

    def test_descriptor_is_compiler_precise_read_only_and_workspace_scoped(self):
        provider = self._provider()
        descriptor = provider.descriptor()
        self.assertEqual(descriptor.id, "scip.fixture")
        self.assertEqual(descriptor.layer, "compiler-index")
        self.assertEqual(descriptor.trust_ceiling, "semantic")
        self.assertEqual(descriptor.lifecycle, "workspace-scoped")
        self.assertFalse(descriptor.incremental)
        self.assertFalse(descriptor.source_authority)
        self.assertFalse(descriptor.mutation_authority)
        self.assertEqual(
            descriptor.capabilities,
            frozenset({"definition", "references", "document-symbols", "diagnostics"}),
        )
        self.assertNotIn("rename", descriptor.capabilities)
        self.assertNotIn("code-action", descriptor.capabilities)

    def test_fingerprint_is_stable_and_bound_to_index_and_tool_identity(self):
        provider = self._provider()
        first = provider.provider_fingerprint()
        second = provider.provider_fingerprint()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_definition_and_reference_queries_return_habitat_owned_envelopes(self):
        provider = self._provider()
        definition = provider.definitions(self.symbol)
        references = provider.references(self.symbol)
        for envelope in (definition, references):
            self.assertEqual(envelope["provider_id"], "scip.fixture")
            self.assertEqual(envelope["activation_revision"], "rev-1")
            self.assertEqual(envelope["trust"], "semantic")
            self.assertEqual(envelope["index_digest"], provider.snapshot.index_digest)
            self.assertEqual(envelope["tool"]["name"], "scip-python")
            self.assertEqual(envelope["provider_fingerprint"], provider.provider_fingerprint())
            self.assertEqual(envelope["symbol"], self.symbol)
        self.assertEqual(definition["locations"][0]["path"], "src/a.py")
        self.assertEqual(definition["locations"][0]["source_digest"], provider.source_digests["src/a.py"])
        self.assertEqual(references["locations"][0]["path"], "src/b.py")

    def test_document_query_normalizes_symbols_diagnostics_and_occurrences(self):
        provider = self._provider()
        document = provider.document("src/b.py")
        self.assertEqual(document["provider_id"], "scip.fixture")
        self.assertEqual(document["path"], "src/b.py")
        self.assertEqual(document["source_digest"], provider.source_digests["src/b.py"])
        self.assertEqual(document["diagnostics"][0]["message"], "fixture warning")
        self.assertEqual(document["occurrences"][0]["symbol"], self.symbol)

    def test_parse_surface_is_explicitly_query_only(self):
        provider = self._provider()
        result = provider.parse(self.root, self.root / "src" / "a.py", "def foo(): pass", "file-1")
        self.assertFalse(result.available)
        self.assertIn("query-oriented", result.reason)


if __name__ == "__main__":
    unittest.main()
