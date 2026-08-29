from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from habitat.benchmarking import BENCHMARK_CLASSES
from benchmarks.heldout_evaluator import evaluate_fixture
from benchmarks.heldout_fixtures import (
    FOUNDATION_HELDOUT_SUITE_PATH,
    MaterializedFixture,
    materialize_fixture,
)


def tree_snapshot(root: Path) -> tuple[tuple[str, str], ...]:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        rows.append((rel, sha256(path.read_bytes()).hexdigest()))
    return tuple(rows)


def solve_retrieval_fixture(root: Path) -> None:
    target = None
    for line in (root / "config" / "runtime.cfg").read_text(encoding="utf-8").splitlines():
        if line.startswith("target="):
            target = line.split("=", 1)[1]
            break
    if target is None:
        raise AssertionError("fixture did not expose runtime target")
    (root / "answer.txt").write_text(target + "\n", encoding="utf-8")


class HeldOutCatalogTests(unittest.TestCase):
    def test_catalog_covers_all_benchmark_classes(self):
        payload = json.loads(FOUNDATION_HELDOUT_SUITE_PATH.read_text(encoding="utf-8"))
        self.assertEqual("foundation-heldout-v1", payload["suite_id"])
        tasks = payload["tasks"]
        self.assertGreaterEqual(len(tasks), len(BENCHMARK_CLASSES))
        self.assertEqual(
            set(BENCHMARK_CLASSES),
            {task["benchmark_class"] for task in tasks},
        )
        self.assertEqual(len(tasks), len({task["id"] for task in tasks}))
        self.assertEqual(len(tasks), len({task["fixture_id"] for task in tasks}))


class FixtureMaterializationTests(unittest.TestCase):
    def test_materialized_fixture_is_frozen(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            fixture = materialize_fixture("retrieval-orientation-v1", root, "nonce-a")
            self.assertIsInstance(fixture, MaterializedFixture)
            with self.assertRaises(FrozenInstanceError):
                fixture.fixture_id = "other"

    def test_same_fixture_and_nonce_are_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            first_root = Path(td) / "first"
            second_root = Path(td) / "second"
            first = materialize_fixture("semantic-navigation-v1", first_root, "nonce-same")
            second = materialize_fixture("semantic-navigation-v1", second_root, "nonce-same")
            self.assertEqual(first.repository_revision, second.repository_revision)
            self.assertEqual(first.task_fingerprint, second.task_fingerprint)
            self.assertEqual(first.evaluator_payload, second.evaluator_payload)
            self.assertEqual(tree_snapshot(first_root), tree_snapshot(second_root))

    def test_different_nonce_changes_mutation_bound_source_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            first_root = Path(td) / "first"
            second_root = Path(td) / "second"
            first = materialize_fixture("debugging-v1", first_root, "nonce-a")
            second = materialize_fixture("debugging-v1", second_root, "nonce-b")
            self.assertNotEqual(first.repository_revision, second.repository_revision)
            self.assertNotEqual(first.task_fingerprint, second.task_fingerprint)
            self.assertNotEqual(tree_snapshot(first_root), tree_snapshot(second_root))

    def test_evaluator_oracle_and_raw_nonce_never_leak_into_agent_tree(self):
        raw_nonce = "TOP-SECRET-MUTATION-NONCE-713"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            fixture = materialize_fixture("adversarial-authority-v1", root, raw_nonce)
            combined = b"\n".join(
                path.read_bytes() for path in root.rglob("*") if path.is_file()
            )
            self.assertNotIn(raw_nonce.encode("utf-8"), combined)
            for forbidden in (b"expected_tree", b"oracle_token", b"evaluator_payload"):
                self.assertNotIn(forbidden, combined)
            self.assertIn("expected_tree", fixture.evaluator_payload)
            self.assertIn("oracle_token", fixture.evaluator_payload)

    def test_materialization_rejects_unknown_traversal_and_unsafe_destination(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with self.assertRaises(ValueError):
                materialize_fixture("../retrieval-orientation-v1", base / "traversal", "nonce")
            with self.assertRaises(KeyError):
                materialize_fixture("unknown-fixture", base / "unknown", "nonce")

            nonempty = base / "nonempty"
            nonempty.mkdir()
            (nonempty / "keep.txt").write_text("do not overwrite\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                materialize_fixture("retrieval-orientation-v1", nonempty, "nonce")
            self.assertEqual("do not overwrite\n", (nonempty / "keep.txt").read_text(encoding="utf-8"))

    def test_large_repository_fixture_is_actually_nontrivial(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "large"
            materialize_fixture("large-repository-scaling-v1", root, "nonce-large")
            python_files = tuple(root.rglob("*.py"))
            self.assertGreaterEqual(len(python_files), 64)
            symbol_lines = 0
            for path in python_files:
                symbol_lines += sum(
                    1
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.startswith("def ") or line.startswith("class ")
                )
            self.assertGreaterEqual(symbol_lines, 128)


class IndependentEvaluatorTests(unittest.TestCase):
    def test_evaluator_returns_independent_boolean_verdict_and_detects_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            fixture = materialize_fixture("retrieval-orientation-v1", root, "nonce-eval")

            before = evaluate_fixture(root, fixture.evaluator_payload)
            self.assertIs(before["success"], False)
            self.assertIs(before["hidden_test_success"], False)
            self.assertIs(before["regression_free"], True)

            solve_retrieval_fixture(root)
            solved = evaluate_fixture(root, fixture.evaluator_payload)
            self.assertIs(solved["success"], True)
            self.assertIs(solved["hidden_test_success"], True)
            self.assertIs(solved["regression_free"], True)

            protected = root / "PUBLIC-CONTRACT.txt"
            protected.write_text("tampered\n", encoding="utf-8")
            tampered = evaluate_fixture(root, fixture.evaluator_payload)
            self.assertIs(tampered["success"], False)
            self.assertIs(tampered["regression_free"], False)

    def test_evaluator_cli_reads_stdin_and_rejects_positional_payloads(self):
        base = Path(__file__).parents[1]
        evaluator = base / "benchmarks" / "heldout_evaluator.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            fixture = materialize_fixture("retrieval-orientation-v1", root, "nonce-cli")
            solve_retrieval_fixture(root)
            request = json.dumps(
                {"workspace": str(root), "evaluator_payload": fixture.evaluator_payload}
            )
            proc = subprocess.run(
                [sys.executable, str(evaluator)],
                input=request,
                text=True,
                capture_output=True,
                check=True,
            )
            verdict = json.loads(proc.stdout)
            self.assertIs(verdict["success"], True)

            rejected = subprocess.run(
                [sys.executable, str(evaluator), request],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(0, rejected.returncode)


if __name__ == "__main__":
    unittest.main()
