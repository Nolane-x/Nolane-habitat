from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from habitat.semantic.admission import SemanticAdmissionRegistry
from tests.scip_fixture import document, index_payload, metadata, occurrence, sample_index


class ScipRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "source"
        self.root.mkdir()
        (self.root / "src").mkdir()
        self.a = self.root / "src" / "a.py"
        self.b = self.root / "src" / "b.py"
        self.a.write_text("def foo():\n    pass\n", encoding="utf-8")
        self.b.write_text("x = 1\n\nvalue = foo()\n", encoding="utf-8")
        payload, self.symbol = sample_index()
        self.index_path = Path(self.tempdir.name) / "index.scip"
        self.index_path.write_bytes(payload)
        self.revision = ["rev-1"]
        self.registry = SemanticAdmissionRegistry()

    def tearDown(self):
        self.tempdir.cleanup()

    def _manager(self):
        from habitat.semantic.scip_runtime import ScipRuntimeManager

        return ScipRuntimeManager(self.root, self.registry, lambda: self.revision[0])

    def test_explicit_activation_registers_probes_and_admits_provider(self):
        manager = self._manager()
        self.assertEqual(manager.status()["providers"], [])

        activated = manager.activate(self.index_path, provider_id="scip.fixture")
        self.assertEqual(activated["provider_id"], "scip.fixture")
        self.assertTrue(activated["admitted"])
        self.assertTrue(self.registry.is_admitted("scip.fixture"))
        selected = self.registry.providers_for("definition", language="python")
        self.assertEqual(tuple(provider.id for provider in selected), ("scip.fixture",))

    def test_queries_are_bound_to_current_source_digests(self):
        manager = self._manager()
        manager.activate(self.index_path, provider_id="scip.fixture")

        definition = manager.definitions("scip.fixture", self.symbol)
        reference = manager.references("scip.fixture", self.symbol)
        self.assertEqual(definition["locations"][0]["path"], "src/a.py")
        self.assertIsNotNone(definition["locations"][0]["source_digest"])
        self.assertEqual(reference["locations"][0]["path"], "src/b.py")
        document_view = manager.document("scip.fixture", self.b)
        self.assertEqual(document_view["path"], "src/b.py")

    def test_source_byte_change_rejects_stale_query_without_revision_change(self):
        from habitat.semantic.scip_runtime import ScipStaleIndexError

        manager = self._manager()
        manager.activate(self.index_path, provider_id="scip.fixture")
        self.a.write_text("def foo():\n    return 1\n", encoding="utf-8")

        with self.assertRaises(ScipStaleIndexError):
            manager.definitions("scip.fixture", self.symbol)

    def test_revision_change_revokes_admission_and_rejects_queries(self):
        from habitat.semantic.scip_runtime import ScipStaleIndexError

        manager = self._manager()
        manager.activate(self.index_path, provider_id="scip.fixture")
        self.revision[0] = "rev-2"

        status = manager.status()["providers"][0]
        self.assertFalse(status["admitted"])
        self.assertTrue(status["stale"])
        self.assertFalse(self.registry.is_admitted("scip.fixture"))
        with self.assertRaises(ScipStaleIndexError):
            manager.references("scip.fixture", self.symbol)

    def test_missing_indexed_source_is_reported_and_cannot_be_returned_as_current_evidence(self):
        from habitat.semantic.scip_runtime import ScipStaleIndexError

        symbol = "scip-python python demo 1.0 missing()."
        item = occurrence(symbol, roles=1, typed_single=(0, 0, 7))
        payload = index_payload(metadata_payload=metadata(), documents=(document("missing.py", occurrences=(item,)),))
        path = Path(self.tempdir.name) / "missing.scip"
        path.write_bytes(payload)
        manager = self._manager()
        manager.activate(path, provider_id="scip.missing")

        status = manager.status()["providers"][0]
        self.assertEqual(status["missing_documents"], ["missing.py"])
        with self.assertRaises(ScipStaleIndexError):
            manager.definitions("scip.missing", symbol)

    def test_close_revokes_admission_and_reactivation_rebinds_same_identity(self):
        manager = self._manager()
        first = manager.activate(self.index_path, provider_id="scip.fixture")
        manager.close_provider("scip.fixture")
        self.assertFalse(self.registry.is_admitted("scip.fixture"))
        second = manager.activate(self.index_path, provider_id="scip.fixture")
        self.assertEqual(first["provider_id"], second["provider_id"])
        self.assertTrue(self.registry.is_admitted("scip.fixture"))


if __name__ == "__main__":
    unittest.main()
