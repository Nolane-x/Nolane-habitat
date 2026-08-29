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


class StrongHarnessExecutionTests(unittest.TestCase):
    def _command(self, path: Path) -> str:
        return f'"{sys.executable}" "{path}"'

    def _write_agent(self, path: Path, runner: str) -> None:
        path.write_text(
            """from hashlib import sha256
import json
from pathlib import Path
import sys

payload = json.load(sys.stdin)
serialized = json.dumps(payload, sort_keys=True)
if any(secret in serialized for secret in ("evaluator_payload", "expected_tree", "oracle_token")):
    raise SystemExit("evaluator oracle leaked to agent")
repo = Path(payload["repo"])
rows = []
for item in sorted(p for p in repo.rglob("*") if p.is_file()):
    rows.append(item.relative_to(repo).as_posix().encode("utf-8") + b"\\0" + item.read_bytes())
initial_tree_sha256 = sha256(b"\\n".join(rows)).hexdigest()
target = None
for line in (repo / "config" / "runtime.cfg").read_text(encoding="utf-8").splitlines():
    if line.startswith("target="):
        target = line.split("=", 1)[1]
        break
if target is None:
    raise SystemExit("missing runtime target")
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
print(json.dumps({
    "task_id": payload["task_id"],
    "success": True,
    "tool_calls": 1,
    "input_tokens": 11,
    "output_tokens": 7,
    "wall_ms": 1,
    "model_id": control["model_id"],
    "scaffold_id": control["scaffold_id"],
    "runner": RUNNER,
    "initial_tree_sha256": initial_tree_sha256,
    "execution_receipt": receipt,
}))
""".replace("RUNNER", repr(runner)),
            encoding="utf-8",
        )

    def test_strong_mode_executes_one_bound_snapshot_across_same_scaffold_conditions(self):
        base = Path(__file__).parents[1]
        evaluator = base / "benchmarks" / "heldout_evaluator.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite = root / "suite.json"
            suite.write_text(
                json.dumps(
                    {
                        "suite_id": "strong-execution-test",
                        "tasks": [
                            {
                                "id": "retrieval-strong",
                                "benchmark_class": "retrieval/orientation",
                                "fixture_id": "retrieval-orientation-v1",
                                "prompt": "Locate the runtime target and write it to answer.txt.",
                                "budget": {"max_steps": 12},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            baseline_agent = root / "baseline_agent.py"
            habitat_agent = root / "habitat_agent.py"
            self._write_agent(baseline_agent, "filesystem-runner")
            self._write_agent(habitat_agent, "habitat-runner")
            out = root / "report.json"
            harness = base / "benchmarks" / "agent_ab_harness.py"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(harness),
                    "--strong-evidence",
                    "--suite",
                    str(suite),
                    "--baseline-cmd",
                    self._command(baseline_agent),
                    "--habitat-cmd",
                    self._command(habitat_agent),
                    "--evaluator-cmd",
                    self._command(evaluator),
                    "--repetitions",
                    "3",
                    "--seed",
                    "41",
                    "--model-id",
                    "model-x",
                    "--scaffold-id",
                    "scaffold-x",
                    "--evaluator-id",
                    "heldout-evaluator-v1",
                    "--environment-fingerprint",
                    "env-x",
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
            self.assertEqual(3, report["schema"])
            self.assertTrue(report["strong_evidence_mode"])
            self.assertEqual(9, len(report["runs"]))
            self.assertEqual(1, len(report["benchmark_lab"]["experiments"]))
            experiment = report["benchmark_lab"]["experiments"][0]
            self.assertEqual([41, 42, 43], experiment["plan"]["seeds"])
            self.assertTrue(experiment["complete"])
            self.assertEqual([], experiment["missing_run_identities"])

            runs = report["runs"]
            self.assertEqual(
                {"filesystem", "habitat"},
                {run["arm"] for run in runs},
            )
            self.assertEqual(
                3,
                sum(run["runner"] == "filesystem-runner" for run in runs),
            )
            self.assertEqual(
                6,
                sum(run["runner"] == "habitat-runner" for run in runs),
            )
            self.assertEqual(1, len({run["initial_tree_sha256"] for run in runs}))
            self.assertEqual(9, len({run["planned_run_identity"] for run in runs}))
            self.assertTrue(all(run["evaluation"]["success"] for run in runs))
            self.assertTrue(all(run["receipt_valid"] for run in runs))

            condition_ids = {run["condition_id"] for run in runs}
            self.assertIn("filesystem", condition_ids)
            self.assertIn("habitat", condition_ids)
            ablation_conditions = condition_ids - {"filesystem", "habitat"}
            self.assertEqual(1, len(ablation_conditions))
            ablation_condition = next(iter(ablation_conditions))
            self.assertTrue(ablation_condition.startswith("habitat:"))

            for run in runs:
                receipt = run["execution_receipt"]
                self.assertEqual(run["planned_run_identity"], receipt["planned_run_identity"])
                self.assertEqual(run["condition_id"], receipt["condition_id"])
                self.assertEqual(run["repetition"], receipt["repetition"])
                self.assertEqual(run["seed"], receipt["seed"])
                self.assertEqual("env-x", receipt["environment_fingerprint"])
                self.assertEqual("model-x", receipt["model_id"])
                self.assertEqual("scaffold-x", receipt["scaffold_id"])
                self.assertEqual("heldout-evaluator-v1", receipt["evaluator_id"])


if __name__ == "__main__":
    unittest.main()
