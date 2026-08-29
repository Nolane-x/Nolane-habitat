from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Mapping


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _safe_workspace_path(workspace: Path, relative: str) -> Path:
    candidate = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError(f"unsafe evaluator path: {relative!r}")
    root = workspace.resolve()
    resolved = root.joinpath(*candidate.parts).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"evaluator path escapes workspace: {relative!r}") from exc
    return resolved


def _payload_is_valid(payload: Mapping[str, object]) -> bool:
    token = payload.get("oracle_token")
    if not isinstance(token, str) or not token:
        return False
    body = dict(payload)
    body.pop("oracle_token", None)
    return sha256(_canonical_json(body)).hexdigest() == token


def _check_regression(
    workspace: Path,
    expected_tree: Mapping[str, object],
    protected_paths: object,
) -> bool:
    if not isinstance(protected_paths, list):
        return False
    for relative in protected_paths:
        if not isinstance(relative, str):
            return False
        expected = expected_tree.get(relative)
        if not isinstance(expected, str):
            return False
        try:
            path = _safe_workspace_path(workspace, relative)
        except ValueError:
            return False
        if not path.is_file():
            return False
        if sha256(path.read_bytes()).hexdigest() != expected:
            return False
    return True


def _evaluate_rule(workspace: Path, rule: object) -> bool:
    if not isinstance(rule, dict):
        return False
    kind = rule.get("kind")

    if kind == "answer_file":
        relative = rule.get("path")
        expected = rule.get("expected")
        if not isinstance(relative, str) or not isinstance(expected, str):
            return False
        try:
            path = _safe_workspace_path(workspace, relative)
        except ValueError:
            return False
        if not path.is_file():
            return False
        return path.read_text(encoding="utf-8").strip() == expected

    if kind == "content_constraints":
        files = rule.get("files")
        if not isinstance(files, dict):
            return False
        for relative, constraints in files.items():
            if not isinstance(relative, str) or not isinstance(constraints, dict):
                return False
            try:
                path = _safe_workspace_path(workspace, relative)
            except ValueError:
                return False
            if not path.is_file():
                return False
            text = path.read_text(encoding="utf-8")
            contains = constraints.get("contains", [])
            not_contains = constraints.get("not_contains", [])
            if not isinstance(contains, list) or not isinstance(not_contains, list):
                return False
            if any(not isinstance(item, str) or item not in text for item in contains):
                return False
            if any(not isinstance(item, str) or item in text for item in not_contains):
                return False
        return True

    return False


def evaluate_fixture(
    workspace: Path,
    evaluator_payload: Mapping[str, object],
) -> dict[str, object]:
    workspace = Path(workspace)
    if not workspace.is_dir():
        raise ValueError("workspace must be an existing directory")
    if not isinstance(evaluator_payload, Mapping):
        raise TypeError("evaluator_payload must be a mapping")

    payload_valid = _payload_is_valid(evaluator_payload)
    expected_tree = evaluator_payload.get("expected_tree")
    if not isinstance(expected_tree, Mapping):
        payload_valid = False
        expected_tree = {}

    regression_free = (
        payload_valid
        and _check_regression(
            workspace,
            expected_tree,
            evaluator_payload.get("protected_paths"),
        )
    )
    hidden_test_success = payload_valid and _evaluate_rule(
        workspace, evaluator_payload.get("rule")
    )
    success = payload_valid and regression_free and hidden_test_success

    return {
        "success": bool(success),
        "hidden_test_success": bool(hidden_test_success),
        "regression_free": bool(regression_free),
        "evaluator_payload_valid": bool(payload_valid),
    }


def _main() -> int:
    if len(sys.argv) != 1:
        print("heldout_evaluator accepts JSON only on stdin", file=sys.stderr)
        return 2
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise TypeError("request must be a JSON object")
        workspace = request.get("workspace")
        payload = request.get("evaluator_payload")
        if not isinstance(workspace, str) or not isinstance(payload, dict):
            raise TypeError("request requires workspace and evaluator_payload")
        verdict = evaluate_fixture(Path(workspace), payload)
    except Exception as exc:
        print(f"heldout evaluator error: {exc}", file=sys.stderr)
        return 2
    json.dump(verdict, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())