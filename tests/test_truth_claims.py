from __future__ import annotations

import math
import unittest
from types import MappingProxyType


class TruthClaimTests(unittest.TestCase):
    def test_mapping_order_does_not_change_value_digest_or_claim_id(self):
        from habitat.truth.authority import AuthorityClass
        from habitat.truth.claims import make_truth_claim

        left = make_truth_claim(
            subject="symbol:demo.f",
            predicate="definition",
            value={"b": [2, 3], "a": {"y": False, "x": 1}},
            authority_class=AuthorityClass.PARSER_DERIVED,
            revision="rev-1",
            producer="parser",
            provenance={"z": 9, "a": "first"},
        )
        right = make_truth_claim(
            subject="symbol:demo.f",
            predicate="definition",
            value={"a": {"x": 1, "y": False}, "b": [2, 3]},
            authority_class=AuthorityClass.PARSER_DERIVED,
            revision="rev-1",
            producer="parser",
            provenance={"a": "first", "z": 9},
        )
        self.assertEqual(left.value_digest, right.value_digest)
        self.assertEqual(left.id, right.id)

    def test_claim_identity_is_bound_to_authority_and_provenance(self):
        from habitat.truth.authority import AuthorityClass
        from habitat.truth.claims import make_truth_claim

        base = dict(
            subject="file:demo.py",
            predicate="digest",
            value="abc",
            revision="rev-1",
            producer="workspace",
        )
        exact = make_truth_claim(
            **base,
            authority_class=AuthorityClass.SOURCE_EXACT,
            provenance={"authority_id": "source-a"},
        )
        semantic = make_truth_claim(
            **base,
            authority_class=AuthorityClass.COMPILER_PRECISE,
            provenance={"authority_id": "source-a"},
        )
        other_source = make_truth_claim(
            **base,
            authority_class=AuthorityClass.SOURCE_EXACT,
            provenance={"authority_id": "source-b"},
        )
        self.assertNotEqual(exact.id, semantic.id)
        self.assertNotEqual(exact.id, other_source.id)

    def test_claim_value_and_provenance_are_deeply_immutable(self):
        from habitat.truth.authority import AuthorityClass
        from habitat.truth.claims import make_truth_claim

        original_value = {"items": [{"name": "a"}]}
        original_provenance = {"providers": ["one"]}
        claim = make_truth_claim(
            subject="symbol:x",
            predicate="facts",
            value=original_value,
            authority_class=AuthorityClass.COMPILER_PRECISE,
            revision="rev-1",
            producer="compiler",
            provenance=original_provenance,
        )
        original_value["items"][0]["name"] = "mutated"
        original_provenance["providers"].append("two")

        self.assertIsInstance(claim.value, MappingProxyType)
        self.assertEqual(claim.value["items"][0]["name"], "a")
        self.assertIsInstance(claim.value["items"], tuple)
        self.assertIsInstance(claim.provenance, MappingProxyType)
        self.assertEqual(claim.provenance["providers"], ("one",))
        with self.assertRaises(TypeError):
            claim.value["new"] = True
        with self.assertRaises(TypeError):
            claim.provenance["new"] = True

    def test_confidence_is_metadata_not_authority_or_identity(self):
        from habitat.truth.authority import AuthorityClass
        from habitat.truth.claims import make_truth_claim

        low = make_truth_claim(
            subject="hypothesis:x",
            predicate="holds",
            value=True,
            authority_class=AuthorityClass.MODEL_INFERRED,
            confidence=0.01,
            revision="rev-1",
            producer="model",
        )
        high = make_truth_claim(
            subject="hypothesis:x",
            predicate="holds",
            value=True,
            authority_class=AuthorityClass.MODEL_INFERRED,
            confidence=0.99,
            revision="rev-1",
            producer="model",
        )
        self.assertIs(low.authority_class, AuthorityClass.MODEL_INFERRED)
        self.assertIs(high.authority_class, AuthorityClass.MODEL_INFERRED)
        self.assertEqual(low.id, high.id)
        self.assertNotEqual(low.confidence, high.confidence)

    def test_non_finite_and_non_json_values_are_rejected(self):
        from habitat.truth.authority import AuthorityClass
        from habitat.truth.claims import make_truth_claim

        common = dict(
            subject="x",
            predicate="value",
            authority_class=AuthorityClass.HEURISTIC_DERIVED,
            revision="rev-1",
            producer="heuristic",
        )
        for value in (math.nan, math.inf, -math.inf, {"bad": object()}):
            with self.subTest(value=repr(value)):
                with self.assertRaises((TypeError, ValueError)):
                    make_truth_claim(value=value, **common)

    def test_unknown_authority_string_is_rejected(self):
        from habitat.truth.claims import make_truth_claim

        with self.assertRaises(ValueError):
            make_truth_claim(
                subject="x",
                predicate="value",
                value=1,
                authority_class="SUPER_TRUSTED",
                revision="rev-1",
                producer="test",
            )

    def test_recalled_origin_authority_is_provenance_not_promotion(self):
        from habitat.truth.authority import AuthorityClass
        from habitat.truth.claims import make_truth_claim

        recalled = make_truth_claim(
            subject="memory:x",
            predicate="statement",
            value="remembered exact fact",
            authority_class=AuthorityClass.MEMORY_RECALLED,
            origin_claim_id="claim-source",
            origin_authority_class=AuthorityClass.SOURCE_EXACT,
            revision="rev-2",
            producer="memory",
        )
        self.assertIs(recalled.authority_class, AuthorityClass.MEMORY_RECALLED)
        self.assertIs(recalled.origin_authority_class, AuthorityClass.SOURCE_EXACT)

        with self.assertRaises(ValueError):
            make_truth_claim(
                subject="memory:x",
                predicate="statement",
                value="bad origin",
                authority_class=AuthorityClass.MEMORY_RECALLED,
                origin_authority_class="UNKNOWN_AUTHORITY",
                revision="rev-2",
                producer="memory",
            )


if __name__ == "__main__":
    unittest.main()
