from __future__ import annotations

import unittest
from pathlib import Path

from habitat.semantic.disagreement import SemanticClaim
from habitat.truth.authority import AuthorityClass
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


class WorkspaceTruthProjectionTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory):
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        target = source / "sample.py"
        target.write_text("def target():\n    return 1\n", encoding="utf-8")
        ws = HabitatWorkspace.create(source, root / "habitat")
        return ws, target

    def test_projection_normalizes_workspace_files_and_symbols(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, _target = self.make_workspace(temp)

            report = ws.truth_projection()

            self.assertEqual(report["revision"], ws.revision)
            self.assertGreaterEqual(report["claim_count"], 2)
            source_claims = [claim for claim in report["claims"] if claim.predicate == "source_snapshot"]
            symbol_claims = [claim for claim in report["claims"] if claim.predicate == "symbol"]
            self.assertEqual(len(source_claims), 1)
            self.assertGreaterEqual(len(symbol_claims), 1)
            self.assertIs(source_claims[0].authority_class, AuthorityClass.SOURCE_EXACT)
            self.assertEqual(source_claims[0].revision, ws.revision)
            self.assertTrue(all(claim.revision == ws.revision for claim in symbol_claims))

    def test_external_source_drift_is_reported_stale_without_refresh(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, target = self.make_workspace(temp)
            indexed_revision = ws.revision
            target.write_text("def target():\n    return 2\n", encoding="utf-8")

            report = ws.truth_projection()

            self.assertEqual(ws.revision, indexed_revision)
            self.assertEqual(report["revision"], indexed_revision)
            self.assertGreater(report["stale_count"], 0)
            stale_source = [
                item
                for item in report["stale_claims"]
                if item.subject == "file:sample.py" and "source-digest-mismatch" in item.reasons
            ]
            self.assertEqual(len(stale_source), 1)

    def test_projection_does_not_start_or_reconcile_semantic_runtimes(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, _target = self.make_workspace(temp)
            self.assertIsNone(ws._lsp_runtime_manager)
            self.assertIsNone(ws._scip_runtime_manager)
            self.assertIsNone(ws._semantic_disagreement_state)
            before = ws.semantic_registry.cache_identity("parse", language="python")

            ws.truth_projection()

            after = ws.semantic_registry.cache_identity("parse", language="python")
            self.assertIsNone(ws._lsp_runtime_manager)
            self.assertIsNone(ws._scip_runtime_manager)
            self.assertIsNone(ws._semantic_disagreement_state)
            self.assertEqual(before, after)

    def test_only_explicitly_supplied_semantic_claims_enter_projection(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, _target = self.make_workspace(temp)
            indexed = ws.store.file_by_path("sample.py")
            semantic = SemanticClaim(
                id="semantic-1",
                subject_key="symbol:target",
                capability="definition",
                provider_id="provider.fixture",
                provider_fingerprint="fixture:v1",
                revision=ws.revision,
                path="sample.py",
                source_digest=str(indexed["digest"]),
                trust="semantic",
                value={"path": "sample.py", "line": 1},
                evidence={"fixture": True},
            )

            without = ws.truth_projection()
            with_explicit = ws.truth_projection(semantic_claims=[semantic])

            self.assertFalse(any(claim.producer == "provider.fixture" for claim in without["claims"]))
            explicit = [claim for claim in with_explicit["claims"] if claim.producer == "provider.fixture"]
            self.assertEqual(len(explicit), 1)
            self.assertIs(explicit[0].authority_class, AuthorityClass.COMPILER_PRECISE)
            self.assertEqual(explicit[0].provider_fingerprint, "fixture:v1")
            self.assertIsNone(ws._lsp_runtime_manager)
            self.assertIsNone(ws._scip_runtime_manager)

    def test_projection_bound_is_deterministic_and_validated(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, _target = self.make_workspace(temp)

            first = ws.truth_projection(max_claims=1)
            second = ws.truth_projection(max_claims=1)

            self.assertEqual(first, second)
            self.assertEqual(first["claim_count"], 1)
            self.assertTrue(first["truncated"])
            with self.assertRaises(ValueError):
                ws.truth_projection(max_claims=0)
            with self.assertRaises(ValueError):
                ws.truth_projection(max_claims=True)


if __name__ == "__main__":
    unittest.main()
