from __future__ import annotations

import unittest


class SemanticDisagreementTests(unittest.TestCase):
    def _claim(self, provider_id: str, value: dict, *, subject: str = "symbol:a.py:foo:function"):
        from habitat.semantic.disagreement import make_claim

        return make_claim(
            subject_key=subject,
            capability="parse",
            provider_id=provider_id,
            provider_fingerprint=f"fp-{provider_id}",
            revision="rev-1",
            path="a.py",
            source_digest="digest-1",
            trust="semantic",
            value=value,
            evidence=(f"provider:{provider_id}",),
        )

    def test_identical_claims_do_not_create_disagreement(self):
        from habitat.semantic.disagreement import compare_claims

        value = {
            "kind": "symbol",
            "name": "foo",
            "qualified_name": "foo",
            "symbol_kind": "function",
            "language": "python",
            "start_line": 1,
            "end_line": 2,
            "signature": "def foo()",
        }
        result = compare_claims(
            {"provider.a": [self._claim("provider.a", value)], "provider.b": [self._claim("provider.b", value)]},
            comparison_complete=True,
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["disagreements"], [])

    def test_signature_difference_is_attribute_conflict(self):
        from habitat.semantic.disagreement import compare_claims

        first = self._claim("provider.a", {
            "kind": "symbol", "name": "foo", "qualified_name": "foo", "symbol_kind": "function",
            "language": "python", "start_line": 1, "end_line": 2, "signature": "def foo(a)"})
        second = self._claim("provider.b", {
            "kind": "symbol", "name": "foo", "qualified_name": "foo", "symbol_kind": "function",
            "language": "python", "start_line": 1, "end_line": 2, "signature": "def foo(a, b)"})
        result = compare_claims({"provider.a": [first], "provider.b": [second]}, comparison_complete=True)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["disagreements"][0].kind, "attribute-conflict")
        self.assertEqual(result["disagreements"][0].resolution, "unresolved")

    def test_range_only_difference_is_location_conflict(self):
        from habitat.semantic.disagreement import compare_claims

        base = {
            "kind": "symbol", "name": "foo", "qualified_name": "foo", "symbol_kind": "function",
            "language": "python", "start_line": 1, "end_line": 2, "signature": "def foo()"}
        moved = dict(base, start_line=3, end_line=4)
        result = compare_claims(
            {"provider.a": [self._claim("provider.a", base)], "provider.b": [self._claim("provider.b", moved)]},
            comparison_complete=True,
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["disagreements"][0].kind, "location-conflict")

    def test_missing_claim_is_presence_conflict_only_when_comparison_complete(self):
        from habitat.semantic.disagreement import compare_claims

        value = {
            "kind": "symbol", "name": "foo", "qualified_name": "foo", "symbol_kind": "function",
            "language": "python", "start_line": 1, "end_line": 2, "signature": "def foo()"}
        claim = self._claim("provider.a", value)
        complete = compare_claims({"provider.a": [claim], "provider.b": []}, comparison_complete=True)
        incomplete = compare_claims({"provider.a": [claim], "provider.b": []}, comparison_complete=False)
        self.assertEqual(complete["count"], 1)
        self.assertEqual(complete["disagreements"][0].kind, "presence-conflict")
        self.assertEqual(incomplete["count"], 0)

    def test_disagreement_ids_are_independent_of_provider_mapping_order(self):
        from habitat.semantic.disagreement import compare_claims

        a = self._claim("provider.a", {
            "kind": "symbol", "name": "foo", "qualified_name": "foo", "symbol_kind": "function",
            "language": "python", "start_line": 1, "end_line": 2, "signature": "def foo(a)"})
        b = self._claim("provider.b", {
            "kind": "symbol", "name": "foo", "qualified_name": "foo", "symbol_kind": "function",
            "language": "python", "start_line": 1, "end_line": 2, "signature": "def foo(b)"})
        first = compare_claims({"provider.a": [a], "provider.b": [b]}, comparison_complete=True)
        second = compare_claims({"provider.b": [b], "provider.a": [a]}, comparison_complete=True)
        self.assertEqual(first["disagreements"][0].id, second["disagreements"][0].id)
        self.assertEqual(first["disagreements"][0].claims, second["disagreements"][0].claims)

    def test_disagreement_limit_sets_truncated(self):
        from habitat.semantic.disagreement import compare_claims

        claims_a = []
        for index in range(3):
            claims_a.append(self._claim("provider.a", {
                "kind": "symbol", "name": f"f{index}", "qualified_name": f"f{index}", "symbol_kind": "function",
                "language": "python", "start_line": index + 1, "end_line": index + 1, "signature": f"def f{index}()"},
                subject=f"symbol:a.py:f{index}:function"))
        result = compare_claims({"provider.a": claims_a, "provider.b": []}, comparison_complete=True, max_disagreements=2)
        self.assertEqual(result["count"], 2)
        self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()
