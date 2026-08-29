from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class StrongHarnessCliContractTests(unittest.TestCase):
    def _invoke(self, suite: Path, out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        harness = Path(__file__).parents[1] / "benchmarks" / "agent_ab_harness.py"
        args = [
            sys.executable,
            str(harness),
            "--strong-evidence",
            "--suite",
            str(suite),
            "--baseline-cmd",
            sys.executable,
            "--habitat-cmd",
            sys.executable,
            "--out",
            str(out),
            *extra,
        ]
        return subprocess.run(args, text=True, capture_output=True)

    def test_strong_mode_requires_three_repetitions_and_all_causal_identities(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite = root / "suite.json"
            suite.write_text(
                json.dumps(
                    {
                        "suite_id": "strong-contract-test",
                        "tasks": [
                            {
                                "id": "t1",
                                "benchmark_class": "retrieval/orientation",
                                "fixture_id": "retrieval-orientation-v1",
                                "prompt": "Find the target.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            out = root / "out.json"
            required = [
                "--model-id",
                "model-x",
                "--scaffold-id",
                "scaffold-x",
                "--evaluator-id",
                "evaluator-x",
                "--environment-fingerprint",
                "env-x",
                "--evaluator-cmd",
                sys.executable,
            ]

            too_few = self._invoke(
                suite,
                out,
                "--repetitions",
                "2",
                *required,
            )
            self.assertNotEqual(0, too_few.returncode)
            self.assertIn(
                "strong evidence requires at least 3 repetitions",
                too_few.stderr,
            )

            missing_model = self._invoke(
                suite,
                out,
                "--repetitions",
                "3",
                *required[2:],
            )
            self.assertNotEqual(0, missing_model.returncode)
            self.assertIn("--model-id is required in strong evidence mode", missing_model.stderr)

            missing_evaluator_command = self._invoke(
                suite,
                out,
                "--repetitions",
                "3",
                *required[:-2],
            )
            self.assertNotEqual(0, missing_evaluator_command.returncode)
            self.assertIn(
                "--evaluator-cmd is required in strong evidence mode",
                missing_evaluator_command.stderr,
            )


if __name__ == "__main__":
    unittest.main()
