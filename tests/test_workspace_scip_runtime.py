from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from habitat.workspace import HabitatWorkspace
from tests.scip_fixture import sample_index
from tests.support import WorkspaceTemporaryDirectory


class WorkspaceScipRuntimeTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory):
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        (source / "src").mkdir()
        (source / "src" / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
        (source / "src" / "b.py").write_text("x = 1\n\nvalue = foo()\n", encoding="utf-8")
        payload, symbol = sample_index()
        index_path = root / "index.scip"
        index_path.write_bytes(payload)
        ws = HabitatWorkspace.create(source, root / "habitat")
        return ws, index_path, symbol

    def test_scip_status_is_lazy_and_does_not_auto_activate_existing_index(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, index_path, _ = self.make_workspace(temp)
            self.assertTrue(index_path.exists())
            self.assertEqual(ws.scip_status()["providers"], [])
            self.assertFalse(any(provider["id"].startswith("scip.") and provider["admitted"] for provider in ws.semantic_fabric()["providers"]))

    def test_explicit_activation_exposes_read_only_queries_and_fabric_runtime_truth(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, index_path, symbol = self.make_workspace(temp)
            activated = ws.scip_activate(index_path, provider_id="scip.fixture")
            self.assertTrue(activated["admitted"])

            definition = ws.scip_definitions("scip.fixture", symbol)
            references = ws.scip_references("scip.fixture", symbol)
            self.assertEqual(definition["activation_revision"], ws.revision)
            self.assertEqual(definition["locations"][0]["path"], "src/a.py")
            self.assertEqual(references["locations"][0]["path"], "src/b.py")

            report = ws.semantic_fabric()
            provider = next(item for item in report["providers"] if item["id"] == "scip.fixture")
            self.assertTrue(provider["detected"])
            self.assertTrue(provider["admitted"])
            self.assertEqual(provider["layer"], "compiler-index")
            self.assertEqual(set(provider["capabilities"]), {"definition", "references", "document-symbols", "diagnostics"})
            self.assertNotIn("rename", provider["capabilities"])

    def test_refresh_invalidates_admission_until_explicit_reactivation(self):
        from habitat.semantic.scip_runtime import ScipStaleIndexError

        with WorkspaceTemporaryDirectory() as temp:
            ws, index_path, symbol = self.make_workspace(temp)
            ws.scip_activate(index_path, provider_id="scip.fixture")
            (ws.source_root / "src" / "a.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
            ws.refresh("source-change")

            report = ws.semantic_fabric()
            provider = next(item for item in report["providers"] if item["id"] == "scip.fixture")
            self.assertFalse(provider["admitted"])
            with self.assertRaises(ScipStaleIndexError):
                ws.scip_definitions("scip.fixture", symbol)

            reactivated = ws.scip_activate(index_path, provider_id="scip.fixture")
            self.assertTrue(reactivated["admitted"])

    def test_workspace_close_revokes_scip_runtime_before_core_close(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, index_path, _ = self.make_workspace(temp)
            ws.scip_activate(index_path, provider_id="scip.fixture")
            self.assertTrue(ws.semantic_registry.is_admitted("scip.fixture"))
            ws.close()
            self.assertFalse(ws.semantic_registry.is_admitted("scip.fixture"))


if __name__ == "__main__":
    unittest.main()
