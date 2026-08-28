from __future__ import annotations

import unittest
from pathlib import Path

from habitat.model import SymbolRecord
from habitat.semantic.admission import SemanticAdmissionRegistry
from habitat.semantic.base import SemanticParseResult, SemanticProvider
from habitat.util import sha256_file
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


class _WorkspaceProvider(SemanticProvider):
    layer = "test-semantic"
    trust_ceiling = "semantic"
    capabilities = frozenset({"parse"})
    lifecycle = "stateless"
    source_authority = False
    mutation_authority = False
    provenance_required = True

    def __init__(self, provider_id: str, kind: str):
        self.id = provider_id
        self.languages = frozenset({"typescript"})
        self.kind = kind
        self.calls = 0

    def available(self):
        return True, "workspace fixture"

    def provider_fingerprint(self):
        return f"workspace-fixture:{self.id}"

    def parse(self, root: Path, path: Path, text: str, file_id: str):
        self.calls += 1
        return SemanticParseResult(
            provider=self.id,
            available=True,
            symbols=[
                SymbolRecord(
                    id=f"{self.id}-foo",
                    file_id=file_id,
                    path=path.relative_to(root).as_posix(),
                    name="foo",
                    qualified_name="foo",
                    kind=self.kind,
                    language="typescript",
                    start_line=1,
                    end_line=1,
                    signature="function foo(): void",
                    trust="semantic",
                )
            ],
        )


def _fixture_registry(*providers: _WorkspaceProvider) -> SemanticAdmissionRegistry:
    registry = SemanticAdmissionRegistry()
    for provider in providers:
        registry.register(provider)
        registry.probe(provider.id)
        registry.admit(provider.id, evidence=(f"workspace:{provider.id}",))
    return registry


class WorkspaceSemanticDisagreementTests(unittest.TestCase):
    def _workspace(self):
        temp = WorkspaceTemporaryDirectory()
        root = Path(temp.__enter__())
        self.addCleanup(lambda: temp.__exit__(None, None, None))
        source = root / "source"
        source.mkdir()
        target = source / "a.ts"
        target.write_text("export function foo(): void {}\n", encoding="utf-8")
        ws = HabitatWorkspace.create(source, root / "habitat")
        self.addCleanup(ws.close)
        return ws, source, target

    def test_explicit_facade_returns_current_revision_and_digest_bound_disagreement(self):
        ws, _source, target = self._workspace()
        first = _WorkspaceProvider("provider.a", "function")
        second = _WorkspaceProvider("provider.b", "method")
        ws.semantic_registry = _fixture_registry(first, second)

        report = ws.semantic_disagreements(Path("a.ts"))

        self.assertEqual(report["revision"], ws.revision)
        self.assertEqual(report["source_digest"], sha256_file(target))
        self.assertEqual(report["disagreement_count"], 1)
        disagreement = report["disagreements"][0]
        self.assertEqual(disagreement.revision, ws.revision)
        self.assertEqual(disagreement.source_digest, sha256_file(target))
        self.assertEqual(disagreement.resolution, "unresolved")
        self.assertTrue(all(claim.revision == ws.revision for claim in report["claims"]))

    def test_path_escape_is_rejected_before_provider_execution(self):
        ws, source, _target = self._workspace()
        first = _WorkspaceProvider("provider.a", "function")
        second = _WorkspaceProvider("provider.b", "function")
        ws.semantic_registry = _fixture_registry(first, second)
        outside = source.parent / "outside.ts"
        outside.write_text("export const x = 1\n", encoding="utf-8")

        with self.assertRaises(ValueError):
            ws.semantic_disagreements(outside)
        self.assertEqual((first.calls, second.calls), (0, 0))

    def test_external_source_drift_fails_closed_before_provider_execution(self):
        from habitat.semantic.comparison import SemanticComparisonStaleError

        ws, _source, target = self._workspace()
        first = _WorkspaceProvider("provider.a", "function")
        second = _WorkspaceProvider("provider.b", "method")
        ws.semantic_registry = _fixture_registry(first, second)
        target.write_text("export function foo(): number { return 1 }\n", encoding="utf-8")

        with self.assertRaises(SemanticComparisonStaleError):
            ws.semantic_disagreements(Path("a.ts"))
        self.assertEqual((first.calls, second.calls), (0, 0))

    def test_semantic_fabric_does_not_run_comparison_automatically(self):
        ws, _source, _target = self._workspace()
        first = _WorkspaceProvider("provider.a", "function")
        second = _WorkspaceProvider("provider.b", "method")
        ws.semantic_registry = _fixture_registry(first, second)

        before = ws.semantic_fabric()

        self.assertEqual((first.calls, second.calls), (0, 0))
        self.assertNotIn("semantic_disagreement_state", before)

    def test_explicit_comparison_adds_bounded_fabric_summary_without_changing_admission(self):
        ws, _source, _target = self._workspace()
        first = _WorkspaceProvider("provider.a", "function")
        second = _WorkspaceProvider("provider.b", "method")
        registry = _fixture_registry(first, second)
        ws.semantic_registry = registry

        report = ws.semantic_disagreements(Path("a.ts"))
        fabric = ws.semantic_fabric()

        self.assertTrue(registry.is_admitted("provider.a"))
        self.assertTrue(registry.is_admitted("provider.b"))
        self.assertEqual((first.calls, second.calls), (1, 1))
        state = fabric["semantic_disagreement_state"]
        self.assertEqual(state["path"], "a.ts")
        self.assertEqual(state["revision"], report["revision"])
        self.assertEqual(state["disagreement_count"], report["disagreement_count"])
        self.assertEqual(state["comparison_complete"], report["comparison_complete"])
        self.assertEqual(state["truncated"], report["truncated"])
        self.assertNotIn("claims", state)
        self.assertNotIn("disagreements", state)


if __name__ == "__main__":
    unittest.main()
