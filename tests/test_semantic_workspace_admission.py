from __future__ import annotations

import unittest
from pathlib import Path

from habitat.semantic.admission import SemanticAdmissionRegistry
from habitat.semantic.base import SemanticParseResult, SemanticProvider
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


if __name__ == "__main__":
    unittest.main()
