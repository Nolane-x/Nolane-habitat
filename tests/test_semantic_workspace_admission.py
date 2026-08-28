from __future__ import annotations

import unittest
from pathlib import Path

from habitat.semantic.admission import SemanticAdmissionRegistry
from habitat.semantic.base import SemanticParseResult, SemanticProvider
from habitat.semantic.tree_sitter_provider import TreeSitterProvider
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


class _WorkspaceSemanticProvider(SemanticProvider):
    id = "workspace-semantic-test-provider"
    languages = frozenset({"javascript", "typescript"})
    layer = "syntax"
    trust_ceiling = "parser"
    capabilities = frozenset({"parse"})
    lifecycle = "stateless"

    def available(self) -> tuple[bool, str]:
        return True, "workspace semantic test provider available"

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        return SemanticParseResult(self.id, True, reason="workspace registry selected")


def _admitted_registry() -> SemanticAdmissionRegistry:
    registry = SemanticAdmissionRegistry()
    provider = _WorkspaceSemanticProvider()
    descriptor = registry.register(provider)
    registry.probe(descriptor.id)
    registry.admit(descriptor.id, evidence=("test-provider-contract", "test-host-probe"))
    return registry


class SemanticWorkspaceAdmissionTests(unittest.TestCase):
    def test_workspace_registry_controls_refresh_and_cache_identity(self):
        with WorkspaceTemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            (root / "app.ts").write_text("export const value = 1;\n", encoding="utf-8")
            ws = HabitatWorkspace.create(root, Path(td) / "state")

            self.assertIsInstance(ws.semantic_registry, SemanticAdmissionRegistry)

            ws.semantic_registry = _admitted_registry()
            first = ws.refresh(reason="test-admission-runtime-change")
            self.assertEqual(1, first["compiled_files"])
            self.assertEqual(1, first["providers"].get("workspace-semantic-test-provider"))

            second = ws.refresh(reason="test-admission-runtime-stable")
            self.assertEqual(0, second["compiled_files"])
            self.assertEqual(1, second["reused_files"])
            self.assertEqual(1, second["providers"].get("workspace-semantic-test-provider"))

            ws.semantic_registry = SemanticAdmissionRegistry()
            third = ws.reconcile()
            self.assertEqual(1, third["compiled_files"])
            self.assertEqual(1, third["providers"].get("regex-fallback"))

    def test_counterfactual_evaluation_uses_workspace_registry(self):
        with WorkspaceTemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            (root / "app.ts").write_text("export const value = 1;\n", encoding="utf-8")
            ws = HabitatWorkspace.create(root, Path(td) / "state")
            ws.semantic_registry = _admitted_registry()
            ws.refresh(reason="test-counterfactual-registry-baseline")

            world = ws.counterfactual_fork("semantic admission overlay")
            ws.counterfactual_apply(
                world["id"],
                [{"op": "replace_text", "path": "app.ts", "old": "value = 1", "new": "value = 2"}],
            )
            result = ws.counterfactual_evaluate(world["id"])

            path_result = next(item for item in result["paths"] if item["path"] == "app.ts")
            self.assertEqual("workspace-semantic-test-provider", path_result["provider"])

    def test_semantic_fabric_report_uses_workspace_admission_truth(self):
        with WorkspaceTemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            (root / "app.ts").write_text("export const value = 1;\n", encoding="utf-8")
            ws = HabitatWorkspace.create(root, Path(td) / "state")
            ws.semantic_registry = _admitted_registry()

            report = ws.semantic_fabric()
            provider = next(
                (item for item in report["providers"] if item["id"] == "workspace-semantic-test-provider"),
                None,
            )
            self.assertIsNotNone(provider)
            self.assertTrue(provider["detected"])
            self.assertTrue(provider["admitted"])
            self.assertGreaterEqual(report["admitted_count"], 1)

    def test_real_tree_sitter_compilation_and_fabric_share_admission_truth(self):
        available, reason = TreeSitterProvider().available()
        if not available:
            self.skipTest(f"Tree-sitter runtime unavailable: {reason}")

        with WorkspaceTemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            (root / "Greeter.java").write_text(
                "public class Greeter { public String hello() { return \"hi\"; } }\n",
                encoding="utf-8",
            )
            ws = HabitatWorkspace.create(root, Path(td) / "state")

            report = ws.semantic_fabric()
            provider = next((item for item in report["providers"] if item["id"] == "tree-sitter"), None)
            self.assertIsNotNone(provider)
            self.assertTrue(provider["detected"])
            self.assertTrue(provider["admitted"])
            self.assertIn("java", provider["languages"])
            self.assertEqual("parser", provider["trust_ceiling"])
            self.assertEqual(2, report["contract_version"])

            greeter = next(symbol for symbol in ws.store.all_symbols() if symbol["name"] == "Greeter")
            self.assertEqual("java", greeter["language"])
            self.assertEqual("parser", greeter["trust"])

            refresh = ws.refresh(reason="test-tree-sitter-admission-truth-stable")
            self.assertEqual(0, refresh["compiled_files"])
            self.assertEqual(1, refresh["providers"].get("tree-sitter"))


if __name__ == "__main__":
    unittest.main()
