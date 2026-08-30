from __future__ import annotations

import unittest


class SemanticPrecisionMetricContractTests(unittest.TestCase):
    def test_identity_metrics_are_exact_and_unavailable_values_are_not_fabricated(self):
        from benchmarks.semantic_precision_matrix import measure_identities

        expected = {("Alpha", "class"), ("beta", "function")}
        measured = measure_identities(
            expected,
            {("Alpha", "class"), ("noise", "function")},
            provider_id="fixture-provider",
            provider_fingerprint="fixture:1",
        )
        self.assertIs(measured["available"], True)
        self.assertEqual(measured["true_positive"], 1)
        self.assertEqual(measured["false_positive"], 1)
        self.assertEqual(measured["false_negative"], 1)
        self.assertEqual(measured["precision"], 0.5)
        self.assertEqual(measured["recall"], 0.5)

        unavailable = measure_identities(
            expected,
            None,
            provider_id="missing-provider",
            provider_fingerprint=None,
            unavailable_reason="fixture provider unavailable",
        )
        self.assertIs(unavailable["available"], False)
        self.assertIsNone(unavailable["observed_count"])
        self.assertIsNone(unavailable["true_positive"])
        self.assertIsNone(unavailable["false_positive"])
        self.assertIsNone(unavailable["false_negative"])
        self.assertIsNone(unavailable["precision"])
        self.assertIsNone(unavailable["recall"])
        self.assertEqual(unavailable["reason"], "fixture provider unavailable")


class SemanticPrecisionMatrixContractTests(unittest.TestCase):
    def test_real_matrix_measures_python_and_typescript_with_two_distinct_provider_lanes(self):
        from benchmarks.semantic_precision_matrix import build_report

        report = build_report()
        self.assertEqual(report["schema"], "nolane-semantic-precision-matrix-v1")
        self.assertEqual(set(report["languages"]), {"python", "typescript"})
        self.assertIs(report["coverage_admissible"], True)

        for language in ("python", "typescript"):
            with self.subTest(language=language):
                block = report["languages"][language]
                self.assertGreater(block["expected_count"], 0)
                self.assertEqual(
                    {item["lane"] for item in block["measurements"]},
                    {"habitat-compiler", "tree-sitter"},
                )
                available = [item for item in block["measurements"] if item["available"]]
                self.assertEqual(len(available), 2)
                self.assertGreaterEqual(len({item["provider_id"] for item in available}), 2)
                for item in available:
                    self.assertIsNotNone(item["provider_id"])
                    self.assertIsNotNone(item["precision"])
                    self.assertIsNotNone(item["recall"])
                    self.assertEqual(
                        item["true_positive"] + item["false_negative"],
                        item["expected_count"],
                    )
                    self.assertEqual(
                        item["true_positive"] + item["false_positive"],
                        item["observed_count"],
                    )

        self.assertIn("descriptive", report["claim_boundary"].lower())
        self.assertIn("not", report["claim_boundary"].lower())


if __name__ == "__main__":
    unittest.main()
