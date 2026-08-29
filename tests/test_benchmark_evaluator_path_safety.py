from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.heldout_evaluator import evaluate_fixture


def signed_evaluator_payload(rule: dict[str, object]) -> dict[str, object]:
    body: dict[str, object] = {
        "schema": 1,
        "fixture_id": "path-safety-test",
        "repository_revision": "path-safety-test",
        "task_fingerprint": "path-safety-test",
        "expected_tree": {},
        "protected_paths": [],
        "rule": rule,
    }
    payload = dict(body)
    payload["oracle_token"] = sha256(
        json.dumps(
            body,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return payload


class IndependentEvaluatorPathSafetyTests(unittest.TestCase):
    def test_evaluator_rejects_windows_style_workspace_escape(self):
        relative = ".." + chr(92) + "outside.txt"
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / "repo"
            root.mkdir()
            escape = root / relative
            escape.write_text("escape\n", encoding="utf-8")
            payload = signed_evaluator_payload(
                {"kind": "answer_file", "path": relative, "expected": "escape"}
            )

            verdict = evaluate_fixture(root, payload)

            self.assertIs(verdict["evaluator_payload_valid"], True)
            self.assertIs(verdict["regression_free"], True)
            self.assertIs(verdict["hidden_test_success"], False)
            self.assertIs(verdict["success"], False)

    def test_evaluator_rejects_symlink_target_outside_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / "repo"
            root.mkdir()
            outside = base / "outside.txt"
            outside.write_text("escape\n", encoding="utf-8")
            link = root / "answer.txt"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            payload = signed_evaluator_payload(
                {"kind": "answer_file", "path": "answer.txt", "expected": "escape"}
            )

            verdict = evaluate_fixture(root, payload)

            self.assertIs(verdict["evaluator_payload_valid"], True)
            self.assertIs(verdict["regression_free"], True)
            self.assertIs(verdict["hidden_test_success"], False)
            self.assertIs(verdict["success"], False)


if __name__ == "__main__":
    unittest.main()