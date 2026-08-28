from __future__ import annotations

import json
import unittest

from habitat.model import FileRecord, SymbolRecord
from habitat.semantic.disagreement import SemanticClaim


class TruthAdapterTests(unittest.TestCase):
    def test_public_truth_package_exports_all_adapter_interfaces(self):
        import habitat.truth as truth

        expected = {
            "claim_from_file_record",
            "claim_from_symbol_record",
            "claim_from_relation_record",
            "claim_from_diagnostic_record",
            "claim_from_occurrence_record",
            "claim_from_evidence_row",
            "claim_from_semantic_claim",
            "claim_from_epistemic_item",
            "claim_from_memory",
        }
        self.assertTrue(expected.issubset(set(truth.__all__)))
        for name in expected:
            self.assertTrue(callable(getattr(truth, name)))

    def test_file_record_is_exact_source_snapshot(self):
        from habitat.truth.adapters import claim_from_file_record
        from habitat.truth.authority import AuthorityClass

        record = FileRecord(
            id="file-1", path="demo.py", language="python", size=12,
            digest="d" * 64, mtime_ns=123, indexed_text="x = 1\n",
            indexed_bytes=6, index_truncated=False, parse_complete=True,
        )
        claim = claim_from_file_record(record, revision="rev-1")
        self.assertIs(claim.authority_class, AuthorityClass.SOURCE_EXACT)
        self.assertEqual(claim.subject, "file:demo.py")
        self.assertEqual(claim.predicate, "source_snapshot")
        self.assertEqual(claim.path, "demo.py")
        self.assertEqual(claim.source_digest, record.digest)
        self.assertEqual(claim.canonical_value()["digest"], record.digest)

    def test_legacy_symbol_trust_mapping_is_conservative(self):
        from habitat.truth.adapters import claim_from_symbol_record
        from habitat.truth.authority import AuthorityClass

        expected = {
            "exact": AuthorityClass.SOURCE_EXACT,
            "semantic": AuthorityClass.COMPILER_PRECISE,
            "parser": AuthorityClass.PARSER_DERIVED,
            "heuristic": AuthorityClass.HEURISTIC_DERIVED,
            "derived": AuthorityClass.HEURISTIC_DERIVED,
        }
        for trust, authority in expected.items():
            with self.subTest(trust=trust):
                record = SymbolRecord(
                    id=f"symbol-{trust}", file_id="file-1", path="demo.py",
                    name="f", qualified_name="demo.f", kind="function",
                    language="python", start_line=1, end_line=2, trust=trust,
                )
                claim = claim_from_symbol_record(record, revision="rev-1", source_digest="a" * 64)
                self.assertIs(claim.authority_class, authority)
                self.assertEqual(claim.trust, trust)

    def test_unknown_legacy_trust_fails_closed(self):
        from habitat.truth.adapters import claim_from_evidence_row, claim_from_symbol_record

        symbol = {
            "id": "symbol-x", "file_id": "file-1", "path": "demo.py",
            "name": "f", "qualified_name": "demo.f", "kind": "function",
            "language": "python", "start_line": 1, "end_line": 2, "trust": "super",
        }
        with self.assertRaises(ValueError):
            claim_from_symbol_record(symbol, revision="rev-1", source_digest="a" * 64)

        evidence = {
            "id": "e-1", "kind": "finding", "revision": "rev-1", "path": None,
            "object_id": None, "severity": "info", "summary": "x", "trust": "super",
            "source": "test", "data_json": "{}", "created_at": "2026-08-28T00:00:00Z", "active": 1,
        }
        with self.assertRaises(ValueError):
            claim_from_evidence_row(evidence)

    def test_generic_evidence_payload_cannot_self_upgrade_authority(self):
        from habitat.truth.adapters import claim_from_evidence_row
        from habitat.truth.authority import AuthorityClass

        row = {
            "id": "e-1", "kind": "finding", "revision": "rev-1", "path": "demo.py",
            "object_id": "symbol-1", "severity": "warning", "summary": "possible issue",
            "trust": "heuristic", "source": "scanner",
            "data_json": json.dumps({"authority_class": "SOURCE_EXACT", "confidence": 1.0}),
            "created_at": "2026-08-28T00:00:00Z", "active": 1,
        }
        claim = claim_from_evidence_row(row)
        self.assertIs(claim.authority_class, AuthorityClass.HEURISTIC_DERIVED)
        self.assertEqual(claim.confidence, 1.0)
        self.assertEqual(claim.canonical_provenance()["evidence_id"], "e-1")

    def test_semantic_claim_is_never_promoted_to_source_exact(self):
        from habitat.truth.adapters import claim_from_semantic_claim
        from habitat.truth.authority import AuthorityClass

        semantic = SemanticClaim(
            id="claim-1", subject_key="symbol:demo.f", capability="definition",
            provider_id="provider", provider_fingerprint="fingerprint", revision="rev-1",
            path="demo.py", source_digest="a" * 64, trust="exact",
            value={"path": "demo.py", "line": 1}, evidence={"provider": "test"},
        )
        claim = claim_from_semantic_claim(semantic)
        self.assertIs(claim.authority_class, AuthorityClass.COMPILER_PRECISE)
        self.assertEqual(claim.provider_fingerprint, "fingerprint")
        self.assertEqual(claim.source_digest, "a" * 64)
        self.assertEqual(claim.canonical_provenance()["semantic_claim_id"], "claim-1")

    def test_epistemic_item_is_always_model_inferred(self):
        from habitat.truth.adapters import claim_from_epistemic_item
        from habitat.truth.authority import AuthorityClass

        row = {
            "id": "epi-1", "kind": "hypothesis", "statement": "cache is stale",
            "status": "active", "confidence": 0.98, "scope": "workspace",
            "agent_id": "agent-a", "episode_id": "episode-a", "base_revision": "rev-1",
            "provenance_json": json.dumps({"authority_class": "SOURCE_EXACT"}),
            "invalidation_json": "[]", "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:01:00Z",
        }
        claim = claim_from_epistemic_item(row)
        self.assertIs(claim.authority_class, AuthorityClass.MODEL_INFERRED)
        self.assertEqual(claim.confidence, 0.98)

    def test_memory_wrapper_remains_recalled_and_preserves_valid_origin_only_as_provenance(self):
        from habitat.truth.adapters import claim_from_memory
        from habitat.truth.authority import AuthorityClass

        row = {
            "id": "memory-1", "kind": "fact", "statement": "demo.py existed",
            "status": "active", "scope": "workspace", "agent_id": "agent-a",
            "episode_id": "episode-a", "base_revision": "rev-2", "confidence": 1.0,
            "provenance_json": json.dumps({
                "origin_claim_id": "truth-source",
                "origin_authority_class": "SOURCE_EXACT",
            }),
            "evidence_json": "[]", "valid_until_revision": None, "supersedes": None,
            "invalidated_by": None, "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:01:00Z",
        }
        claim = claim_from_memory(row)
        self.assertIs(claim.authority_class, AuthorityClass.MEMORY_RECALLED)
        self.assertIs(claim.origin_authority_class, AuthorityClass.SOURCE_EXACT)
        self.assertEqual(claim.origin_claim_id, "truth-source")

        bad = dict(row)
        bad["provenance_json"] = json.dumps({"origin_authority_class": "NOT_REAL"})
        with self.assertRaises(ValueError):
            claim_from_memory(bad)


if __name__ == "__main__":
    unittest.main()
