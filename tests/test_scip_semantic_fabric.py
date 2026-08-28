from __future__ import annotations

import unittest
from pathlib import Path

from habitat.workspace import HabitatWorkspace
from tests.scip_fixture import sample_index
from tests.support import WorkspaceTemporaryDirectory


class ScipSemanticFabricTests(unittest.TestCase):
    def test_explicit_activation_reports_precise_read_only_provenance(self):
        with WorkspaceTemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "src").mkdir()
            (source / "src" / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            (source / "src" / "b.py").write_text("x = 1\n\nvalue = foo()\n", encoding="utf-8")
            payload, _ = sample_index()
            index_path = root / "index.scip"
            index_path.write_bytes(payload)
            ws = HabitatWorkspace.create(source, root / "habitat")

            before = ws.semantic_fabric()
            self.assertFalse(any(item["id"] == "scip.fixture" for item in before["providers"]))

            activated = ws.scip_activate(index_path, provider_id="scip.fixture")
            report = ws.semantic_fabric()
            provider = next(item for item in report["providers"] if item["id"] == "scip.fixture")

            self.assertTrue(provider["detected"])
            self.assertTrue(provider["admitted"])
            self.assertEqual(provider["layer"], "compiler-index")
            self.assertEqual(provider["trust_ceiling"], "semantic")
            self.assertEqual(provider["lifecycle"], "workspace-scoped")
            self.assertFalse(provider["incremental"])
            self.assertEqual(
                set(provider["capabilities"]),
                {"definition", "references", "document-symbols", "diagnostics"},
            )
            self.assertNotIn("rename", provider["capabilities"])
            self.assertNotIn("code-action", provider["capabilities"])

            evidence = set(provider["admission_evidence"])
            self.assertIn(f"scip.index.sha256={activated['index_digest']}", evidence)
            self.assertIn("scip.tool.name=fixture-indexer", evidence)
            self.assertIn("scip.tool.version=1.2.3", evidence)
            self.assertIn("scip.project_root=file:///repo", evidence)
            self.assertIn(f"scip.activation_revision={ws.revision}", evidence)
            self.assertTrue(any(item.startswith("scip.documents.sha256=") for item in evidence))
            self.assertIn(
                f"scip.provider.sha256={activated['provider_fingerprint']}",
                evidence,
            )

            self.assertGreaterEqual(report["admitted_count"], 1)


if __name__ == "__main__":
    unittest.main()
