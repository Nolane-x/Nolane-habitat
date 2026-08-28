from __future__ import annotations

import inspect
import unittest


class TruthAuthorityTests(unittest.TestCase):
    def test_authority_taxonomy_is_exact_and_string_valued(self):
        from habitat.truth.authority import AuthorityClass

        self.assertEqual(
            {item.value for item in AuthorityClass},
            {
                "SOURCE_EXACT",
                "OBSERVED_EXACT",
                "COMPILER_PRECISE",
                "PARSER_DERIVED",
                "HEURISTIC_DERIVED",
                "MODEL_INFERRED",
                "MEMORY_RECALLED",
            },
        )
        self.assertTrue(all(isinstance(item.value, str) for item in AuthorityClass))

    def test_legacy_trust_mapping_is_conservative_and_unknown_fails_closed(self):
        from habitat.truth.authority import AuthorityClass, legacy_authority

        self.assertIs(legacy_authority("exact"), AuthorityClass.SOURCE_EXACT)
        self.assertIs(legacy_authority("semantic"), AuthorityClass.COMPILER_PRECISE)
        self.assertIs(legacy_authority("parser"), AuthorityClass.PARSER_DERIVED)
        self.assertIs(legacy_authority("heuristic"), AuthorityClass.HEURISTIC_DERIVED)
        self.assertIs(legacy_authority("derived"), AuthorityClass.HEURISTIC_DERIVED)
        self.assertIsNone(legacy_authority("model"))
        self.assertIsNone(legacy_authority(""))
        self.assertIsNone(legacy_authority(None))

    def test_kernel_exposes_no_numeric_authority_rank_api(self):
        import habitat.truth.authority as authority

        forbidden = {
            "AUTHORITY_RANK",
            "AUTHORITY_WEIGHT",
            "authority_rank",
            "authority_strength",
            "compare_authority",
        }
        self.assertTrue(forbidden.isdisjoint(set(dir(authority))))

    def test_operation_declarations_are_explicit_and_inspectable(self):
        from habitat.truth.authority import AuthorityClass, operation_authority

        symbol = operation_authority("replace_symbol_source")
        self.assertEqual(symbol.operation, "replace_symbol_source")
        self.assertEqual(symbol.mode, "evidence-anchor")
        self.assertEqual(symbol.accepted_evidence_authorities, frozenset({AuthorityClass.SOURCE_EXACT}))
        self.assertTrue(symbol.requires_canonical_source)
        self.assertTrue(symbol.requires_source_digest)
        self.assertTrue(symbol.rationale)

        for operation in ("replace_text", "replace_span", "delete_file", "move_file", "create_file"):
            declaration = operation_authority(operation)
            self.assertEqual(declaration.operation, operation)
            self.assertEqual(declaration.mode, "direct-source")
            self.assertEqual(declaration.accepted_evidence_authorities, frozenset())
            self.assertTrue(declaration.requires_canonical_source)

        with self.assertRaises(KeyError):
            operation_authority("not-an-operation")

    def test_replace_symbol_source_accepts_only_exact_evidence_authority(self):
        from habitat.truth.authority import AuthorityClass, operation_allows_evidence

        self.assertTrue(operation_allows_evidence("replace_symbol_source", AuthorityClass.SOURCE_EXACT))
        for authority in (
            AuthorityClass.OBSERVED_EXACT,
            AuthorityClass.COMPILER_PRECISE,
            AuthorityClass.PARSER_DERIVED,
            AuthorityClass.HEURISTIC_DERIVED,
            AuthorityClass.MODEL_INFERRED,
            AuthorityClass.MEMORY_RECALLED,
            None,
        ):
            self.assertFalse(operation_allows_evidence("replace_symbol_source", authority))

    def test_direct_source_operations_do_not_accept_an_evidence_anchor(self):
        from habitat.truth.authority import AuthorityClass, operation_allows_evidence

        for operation in ("replace_text", "replace_span", "delete_file", "move_file", "create_file"):
            self.assertFalse(operation_allows_evidence(operation, AuthorityClass.SOURCE_EXACT))
            self.assertFalse(operation_allows_evidence(operation, AuthorityClass.COMPILER_PRECISE))

    def test_confidence_is_not_an_authorization_input(self):
        from habitat.truth.authority import operation_allows_evidence

        signature = inspect.signature(operation_allows_evidence)
        self.assertNotIn("confidence", signature.parameters)
        with self.assertRaises(TypeError):
            operation_allows_evidence("replace_symbol_source", None, confidence=1.0)


if __name__ == "__main__":
    unittest.main()
