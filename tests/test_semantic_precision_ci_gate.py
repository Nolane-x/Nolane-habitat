from __future__ import annotations

from pathlib import Path
import unittest


class SemanticPrecisionCIGateTests(unittest.TestCase):
    def test_habitat_ci_generates_gating_semantic_precision_artifact(self):
        workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("Run semantic precision matrix evidence", workflow)
        self.assertIn(
            "python benchmarks/semantic_precision_matrix.py --out .test-artifacts/semantic-precision-matrix.json",
            workflow,
        )
        self.assertIn("path: .test-artifacts/", workflow)


if __name__ == "__main__":
    unittest.main()
