from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class StrongEvidenceReportingTests(unittest.TestCase):
    def _command(self, path: Path) -> str:
        return f'"{sys.executable}" "{path}"'

    def _write_agent(self, path: Path, *, tamper_base_habitat_rep1: bool) -> None:
        path.write_text(
            """import json
from pathlib import Path
import sys

payload = json.load(sys.stdin)
repo = Path(payload["repo"])
target = next(
    line.split("=", 1)[1]
    for line in (repo / "config" / "runtime.cfg").read_text(encoding="utf-8").splitlines()
    if line.startswith("target=")
)
(repo / "answer.txt").write_text(target + "\\n", encoding="utf-8")
control = payload["benchmark_control"]
receipt = {
    key: control[key]
    for key in (
        "planned_run_identity",
        "environment_fingerprint",
        "condition_id",
        "repetition",
        "seed",
        "ablation_fingerprint",
        "model_id",
        "scaffold_id",
        "evaluator_id",
    )
}
if TAMPER and control["condition_id"] == "habitat" and control["repetition"] == 1:
    receipt["seed"] += 1000
print(json.dumps({
    "task_id": payload["task_id"],
    "success": True,
    "tool_calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "wall_ms": 0,
    "ingest_ms": 0,
    "model_id": control["model_id"],
    "scaffold_id": control["scaffold_id"],
    "execution_receipt": receipt,
}))
""".replace("TAMPER", "True" if tamper_base_habitat_rep1 else "False"),
            encoding="utf-8",
        )

    def test_invalid_receipt_is_rejected_and_missingness_remains_explicit(self):
        base = Path(__file__).parents[1]
        harness = base / "benchmarks" / "agent_ab_harness.py"
        evaluator = base / "benchmarks" / "heldout_evaluator.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite = root / "suite.json"
            suite.write_text(
                json.dumps(
                    {
                        "suite_id": "strong-report-test",
                        "tasks": [
                            {
                                "id": "retrieval-report",
                                "benchmark_class": "retrieval/orientation",
                                "fixture_id": "retrieval-orientation-v1",
                                "prompt": "Locate the runtime target and write it to answer.txt.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            baseline = root / "baseline.py"
            habitat = root / "habitat.py"
            self._write_agent(baseline, tamper_base_habitat_rep1=False)
            self._write_agent(habitat, tamper_base_habitat_rep1=True)
            out = root / "report.json"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(harness),
                    "--strong-evidence",
                    "--suite",
                    str(suite),
                    "--baseline-cmd",
                    self._command(baseline),
                    "--habitat-cmd",
                    self._command(habitat),
                    "--evaluator-cmd",
                    self._command(evaluator),
                    "--repetitions",
                    "3",
                    "--seed",
                    "51",
                    "--model-id",
                    "model-r",
                    "--scaffold-id",
                    "scaffold-r",
                    "--evaluator-id",
                    "eval-r",
                    "--environment-fingerprint",
                    "env-r",
                    "--habitat-ablation",
                    json.dumps({"disabled_subsystems": ["memory"]}),
                    "--out",
                    str(out),
                ],
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)

            report = json.loads(out.read_text(encoding="utf-8"))
            benchmark_lab = report["benchmark_lab"]
            self.assertEqual("strong-report-test", benchmark_lab["suite_id"])
            self.assertEqual(["retrieval/orientation"], benchmark_lab["class_coverage"])
            self.assertEqual(
                [
                    "semantic navigation",
                    "refactor/rename",
                    "debugging",
                    "multi-file implementation",
                    "test selection",
                    "runtime diagnosis",
                    "UI tasks",
                    "multi-agent invalidation",
                    "adversarial/authority tests",
                    "large repository scaling",
                ],
                benchmark_lab["missing_classes"],
            )

            experiment = benchmark_lab["experiments"][0]
            self.assertFalse(experiment["complete"])
            self.assertEqual(1, len(experiment["missing_run_identities"]))
            self.assertEqual(9, len(experiment["records"]))
            self.assertEqual(8, sum(record["admitted"] for record in experiment["records"]))

            rejected = [record for record in experiment["records"] if not record["admitted"]]
            self.assertEqual(1, len(rejected))
            self.assertEqual("habitat", rejected[0]["condition_id"])
            self.assertEqual(1, rejected[0]["repetition"])
            self.assertEqual("execution-receipt-mismatch", rejected[0]["rejection_reason"])
            self.assertEqual(
                rejected[0]["planned_run_identity"],
                rejected[0]["execution_receipt"]["planned_run_identity"],
            )
            self.assertEqual(
                rejected[0]["seed"] + 1000,
                rejected[0]["execution_receipt"]["seed"],
            )

            admitted = next(record for record in experiment["records"] if record["admitted"])
            metrics = admitted["metrics"]
            self.assertEqual(0, metrics["input_tokens"])
            self.assertEqual(0, metrics["output_tokens"])
            self.assertEqual(0, metrics["tool_calls"])
            self.assertEqual(0, metrics["ingest_ms"])
            self.assertIsNone(metrics["warm_reconcile_ms"])
            self.assertIsNone(metrics["provider_calls"])
            self.assertGreaterEqual(metrics["wall_ms"], 0)

            comparisons = experiment["comparisons"]
            self.assertEqual(2, len(comparisons))
            by_pair = {
                (comparison["baseline_condition_id"], comparison["candidate_condition_id"]): comparison
                for comparison in comparisons
            }
            self.assertIn(("filesystem", "habitat"), by_pair)
            ablation_id = next(
                condition["condition_id"]
                for condition in experiment["plan"]["conditions"]
                if condition["condition_id"].startswith("habitat:")
            )
            self.assertIn(("habitat", ablation_id), by_pair)
            self.assertEqual(2, len(by_pair[("filesystem", "habitat")]["pairs"]))
            self.assertEqual(2, len(by_pair[("habitat", ablation_id)]["pairs"]))

            pair = by_pair[("filesystem", "habitat")]["pairs"][0]
            self.assertEqual(16, len(pair["metric_deltas"]))
            self.assertEqual(
                {"baseline": None, "candidate": None, "delta": None},
                pair["metric_deltas"]["provider_calls"],
            )
            self.assertEqual(
                {"baseline": 0, "candidate": 0, "delta": 0},
                pair["metric_deltas"]["ingest_ms"],
            )
            self.assertNotIn('"mean_', json.dumps(report["benchmark_lab"], sort_keys=True))


if __name__ == "__main__":
    unittest.main()
