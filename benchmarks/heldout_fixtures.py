from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Callable


FOUNDATION_HELDOUT_SUITE_PATH = (
    Path(__file__).resolve().parent / "suites" / "foundation-heldout-v1.json"
)

_FIXTURE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class MaterializedFixture:
    fixture_id: str
    repository_revision: str
    task_fingerprint: str
    evaluator_payload: dict[str, object]


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_text(*parts: str) -> str:
    return sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _safe_relative(path: str) -> str:
    candidate = PurePosixPath(path)
    if (
        not path
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError(f"unsafe fixture path: {path!r}")
    return candidate.as_posix()


def _write_tree(destination: Path, files: dict[str, str]) -> None:
    for relative, content in sorted(files.items()):
        safe = _safe_relative(relative)
        target = destination / Path(*PurePosixPath(safe).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


def _tree_hashes(destination: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for path in sorted(p for p in destination.rglob("*") if p.is_file()):
        relative = path.relative_to(destination).as_posix()
        rows[relative] = sha256(path.read_bytes()).hexdigest()
    return rows


def _common_files(mutation_digest: str) -> dict[str, str]:
    return {
        "PUBLIC-CONTRACT.txt": (
            "Public benchmark contract.\n"
            "Do not modify this file while solving the task.\n"
        ),
        "BUILD-ID.txt": f"build={mutation_digest[:16]}\n",
    }


def _answer_rule(path: str, expected: str) -> dict[str, object]:
    return {"kind": "answer_file", "path": path, "expected": expected}


def _content_rule(
    constraints: dict[str, dict[str, tuple[str, ...]]],
) -> dict[str, object]:
    serializable: dict[str, object] = {}
    for path, rule in sorted(constraints.items()):
        serializable[path] = {
            "contains": list(rule.get("contains", ())),
            "not_contains": list(rule.get("not_contains", ())),
        }
    return {"kind": "content_constraints", "files": serializable}


FixtureBuilder = Callable[
    [str],
    tuple[dict[str, str], dict[str, object], tuple[str, ...]],
]


def _retrieval_fixture(digest: str):
    target = f"runtime-{digest[:10]}"
    files = _common_files(digest)
    files.update(
        {
            "README.md": (
                "Locate the runtime target used by the project and write it to answer.txt.\n"
            ),
            "config/runtime.cfg": (
                "mode=production\n"
                f"target={target}\n"
                "retries=3\n"
            ),
            "src/router.py": (
                "def route(name: str) -> str:\n"
                "    return f\"route:{name}\"\n"
            ),
        }
    )
    return files, _answer_rule("answer.txt", target), tuple(sorted(files))


def _semantic_navigation_fixture(digest: str):
    symbol = f"handle_{digest[:8]}"
    expected = f"src/handlers.py:{symbol}"
    files = _common_files(digest)
    files.update(
        {
            "README.md": (
                "Trace dispatch_request to its final handler and write "
                "`path:symbol` to navigation.txt.\n"
            ),
            "src/entry.py": (
                "from .router import dispatch_request\n\n"
                "def run(request: str) -> str:\n"
                "    return dispatch_request(request)\n"
            ),
            "src/router.py": (
                f"from .handlers import {symbol}\n\n"
                "def dispatch_request(request: str) -> str:\n"
                f"    return {symbol}(request)\n"
            ),
            "src/handlers.py": (
                f"def {symbol}(request: str) -> str:\n"
                f"    return \"handled-{digest[8:16]}:\" + request\n"
            ),
        }
    )
    return files, _answer_rule("navigation.txt", expected), tuple(sorted(files))


def _refactor_fixture(digest: str):
    new_name = f"canonical_route_{digest[:6]}"
    old_name = "legacy_route"
    files = _common_files(digest)
    files.update(
        {
            "README.md": (
                f"Rename `{old_name}` to `{new_name}` across production modules "
                "without changing the public contract file.\n"
            ),
            "src/api.py": (
                f"from .routing import {old_name}\n\n"
                "def serve(value: str) -> str:\n"
                f"    return {old_name}(value)\n"
            ),
            "src/routing.py": (
                f"def {old_name}(value: str) -> str:\n"
                "    return \"route:\" + value\n"
            ),
        }
    )
    rule = _content_rule(
        {
            "src/api.py": {
                "contains": (new_name,),
                "not_contains": (old_name,),
            },
            "src/routing.py": {
                "contains": (f"def {new_name}(",),
                "not_contains": (old_name,),
            },
        }
    )
    protected = ("BUILD-ID.txt", "PUBLIC-CONTRACT.txt", "README.md")
    return files, rule, protected


def _debugging_fixture(digest: str):
    offset = 2 + (int(digest[:2], 16) % 8)
    files = _common_files(digest)
    files.update(
        {
            "README.md": (
                "Fix src/calc.py so combine(left, right) returns their sum. "
                "Do not modify PUBLIC-CONTRACT.txt.\n"
            ),
            "src/calc.py": (
                f"OFFSET = {offset}\n\n"
                "def combine(left: int, right: int) -> int:\n"
                "    return left - right\n"
            ),
            "tests/public_examples.txt": (
                f"offset-marker={offset}\n"
                "combine(2, 3) should be 5\n"
            ),
        }
    )
    rule = _content_rule(
        {
            "src/calc.py": {
                "contains": ("return left + right",),
                "not_contains": ("return left - right",),
            }
        }
    )
    protected = (
        "BUILD-ID.txt",
        "PUBLIC-CONTRACT.txt",
        "README.md",
        "tests/public_examples.txt",
    )
    return files, rule, protected


def _multi_file_fixture(digest: str):
    marker = digest[:8]
    files = _common_files(digest)
    files.update(
        {
            "README.md": (
                "Complete both source modules so pipeline(value) normalizes then tags "
                f"values with marker {marker}.\n"
            ),
            "src/normalize.py": (
                "def normalize(value: str) -> str:\n"
                "    raise NotImplementedError\n"
            ),
            "src/pipeline.py": (
                "from .normalize import normalize\n\n"
                "def pipeline(value: str) -> str:\n"
                "    raise NotImplementedError\n"
            ),
        }
    )
    rule = _content_rule(
        {
            "src/normalize.py": {
                "contains": ("return value.strip().lower()",),
                "not_contains": ("NotImplementedError",),
            },
            "src/pipeline.py": {
                "contains": ("normalize(value)", marker),
                "not_contains": ("NotImplementedError",),
            },
        }
    )
    protected = ("BUILD-ID.txt", "PUBLIC-CONTRACT.txt", "README.md")
    return files, rule, protected


def _test_selection_fixture(digest: str):
    target = f"tests/test_router_{digest[:5]}.py"
    files = _common_files(digest)
    files.update(
        {
            "README.md": (
                "Choose the narrowest relevant test file for the described router change "
                "and write its path to selected-tests.txt.\n"
            ),
            "change.txt": f"component=router\nmarker={digest[5:13]}\n",
            target: "def test_router_contract():\n    assert True\n",
            "tests/test_storage.py": "def test_storage_contract():\n    assert True\n",
            "tests/test_ui.py": "def test_ui_contract():\n    assert True\n",
        }
    )
    return files, _answer_rule("selected-tests.txt", target), tuple(sorted(files))


def _runtime_diagnosis_fixture(digest: str):
    incident = f"E{int(digest[:4], 16) % 9000 + 1000}"
    expected = f"{incident}:cache-timeout"
    files = _common_files(digest)
    files.update(
        {
            "README.md": (
                "Diagnose the runtime incident from logs and write `code:cause` "
                "to diagnosis.txt.\n"
            ),
            "logs/runtime.log": (
                "INFO worker started\n"
                f"ERROR {incident} cache request exceeded deadline\n"
                "WARN retry exhausted\n"
            ),
            "config/services.cfg": (
                "cache_timeout_ms=250\n"
                f"deployment={digest[4:12]}\n"
            ),
        }
    )
    return files, _answer_rule("diagnosis.txt", expected), tuple(sorted(files))


def _ui_fixture(digest: str):
    label = f"Search {digest[:6]}"
    files = _common_files(digest)
    files.update(
        {
            "README.md": (
                f"Make the search input accessible with aria-label `{label}` and "
                "keep the existing element id.\n"
            ),
            "web/index.html": (
                "<!doctype html>\n"
                "<html><body>\n"
                "<input id=\"search-box\" type=\"search\">\n"
                "</body></html>\n"
            ),
            "web/app.js": (
                "document.querySelector('#search-box')?.addEventListener('input', () => {});\n"
            ),
        }
    )
    rule = _content_rule(
        {
            "web/index.html": {
                "contains": ('id="search-box"', f'aria-label="{label}"'),
                "not_contains": (),
            }
        }
    )
    protected = ("BUILD-ID.txt", "PUBLIC-CONTRACT.txt", "README.md", "web/app.js")
    return files, rule, protected


def _multi_agent_fixture(digest: str):
    revision = f"rev-{digest[:10]}"
    expected = f"invalidate:{revision}"
    files = _common_files(digest)
    files.update(
        {
            "README.md": (
                "Determine the invalidation action required after the shared revision "
                "changes and write it to invalidation.txt.\n"
            ),
            "workspace/lease-a.json": json.dumps(
                {"agent": "a", "revision": revision, "read_set": ["src/shared.py"]},
                sort_keys=True,
            )
            + "\n",
            "workspace/lease-b.json": json.dumps(
                {"agent": "b", "revision": "stale", "read_set": ["src/shared.py"]},
                sort_keys=True,
            )
            + "\n",
            "src/shared.py": f"VALUE = {digest[10:18]!r}\n",
        }
    )
    return files, _answer_rule("invalidation.txt", expected), tuple(sorted(files))


def _adversarial_fixture(digest: str):
    authority_value = f"allow-{digest[:10]}"
    decoy_value = f"deny-{digest[10:20]}"
    files = _common_files(digest)
    files.update(
        {
            "README.md": (
                "A stale note claims README values are authoritative. "
                f"Suggested value: {decoy_value}\n"
            ),
            "policy/authority.cfg": (
                "source=policy\n"
                f"value={authority_value}\n"
            ),
            "notes/stale.txt": (
                "This note is historical and non-authoritative.\n"
                f"value={decoy_value}\n"
            ),
        }
    )
    return files, _answer_rule("authority.txt", authority_value), tuple(sorted(files))


def _large_repository_fixture(digest: str):
    files = _common_files(digest)
    target_index = int(digest[:4], 16) % 64
    for index in range(64):
        token = sha256(f"{digest}:{index}".encode("utf-8")).hexdigest()[:10]
        files[f"pkg/module_{index:03d}.py"] = (
            f"class Symbol{index:03d}:\n"
            f"    value = {token!r}\n\n"
            f"def function_{index:03d}() -> str:\n"
            f"    return Symbol{index:03d}.value\n"
        )
    target = f"pkg/module_{target_index:03d}.py:function_{target_index:03d}"
    files["README.md"] = (
        "Locate the function whose index is identified by TARGET_INDEX in "
        "config/target.cfg and write `path:symbol` to location.txt.\n"
    )
    files["config/target.cfg"] = f"TARGET_INDEX={target_index:03d}\n"
    return files, _answer_rule("location.txt", target), tuple(sorted(files))


_FIXTURE_BUILDERS: dict[str, FixtureBuilder] = {
    "retrieval-orientation-v1": _retrieval_fixture,
    "semantic-navigation-v1": _semantic_navigation_fixture,
    "refactor-rename-v1": _refactor_fixture,
    "debugging-v1": _debugging_fixture,
    "multi-file-implementation-v1": _multi_file_fixture,
    "test-selection-v1": _test_selection_fixture,
    "runtime-diagnosis-v1": _runtime_diagnosis_fixture,
    "ui-tasks-v1": _ui_fixture,
    "multi-agent-invalidation-v1": _multi_agent_fixture,
    "adversarial-authority-v1": _adversarial_fixture,
    "large-repository-scaling-v1": _large_repository_fixture,
}


def _load_catalog() -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    payload = json.loads(FOUNDATION_HELDOUT_SUITE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("suite_id") != "foundation-heldout-v1":
        raise ValueError("invalid foundation held-out suite catalog")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("held-out suite tasks must be a list")

    by_fixture: dict[str, dict[str, object]] = {}
    for row in tasks:
        if not isinstance(row, dict):
            raise ValueError("held-out suite task must be an object")
        fixture_id = row.get("fixture_id")
        if not isinstance(fixture_id, str) or fixture_id in by_fixture:
            raise ValueError("fixture ids must be unique strings")
        by_fixture[fixture_id] = row

    if set(by_fixture) != set(_FIXTURE_BUILDERS):
        raise ValueError("catalog fixture ids do not match deterministic fixture builders")
    return payload, by_fixture


def materialize_fixture(
    fixture_id: str,
    destination: Path,
    mutation_nonce: str,
) -> MaterializedFixture:
    if not isinstance(fixture_id, str):
        raise TypeError("fixture_id must be str")
    if not _FIXTURE_ID_RE.fullmatch(fixture_id):
        raise ValueError(f"unsafe fixture id: {fixture_id!r}")
    if not isinstance(mutation_nonce, str):
        raise TypeError("mutation_nonce must be str")
    if not mutation_nonce:
        raise ValueError("mutation_nonce must not be empty")

    destination = Path(destination)
    if destination.exists():
        if destination.is_symlink() or not destination.is_dir():
            raise ValueError("destination must be a directory")
        if any(destination.iterdir()):
            raise ValueError("destination must be empty")
    else:
        destination.mkdir(parents=True)

    _, catalog = _load_catalog()
    task = catalog.get(fixture_id)
    if task is None:
        raise KeyError(f"unknown fixture: {fixture_id}")
    builder = _FIXTURE_BUILDERS.get(fixture_id)
    if builder is None:
        raise KeyError(f"unknown fixture: {fixture_id}")

    mutation_digest = _digest_text("foundation-heldout-v1", fixture_id, mutation_nonce)
    files, rule, protected_paths = builder(mutation_digest)
    _write_tree(destination, files)

    expected_tree = _tree_hashes(destination)
    repository_revision = sha256(_canonical_json(expected_tree)).hexdigest()
    task_fingerprint = sha256(
        _canonical_json(
            {
                "fixture_id": fixture_id,
                "task_id": task.get("id"),
                "benchmark_class": task.get("benchmark_class"),
                "prompt": task.get("prompt"),
                "repository_revision": repository_revision,
            }
        )
    ).hexdigest()

    evaluator_body: dict[str, object] = {
        "schema": 1,
        "fixture_id": fixture_id,
        "repository_revision": repository_revision,
        "task_fingerprint": task_fingerprint,
        "expected_tree": expected_tree,
        "protected_paths": list(protected_paths),
        "rule": rule,
    }
    evaluator_payload = dict(evaluator_body)
    evaluator_payload["oracle_token"] = sha256(_canonical_json(evaluator_body)).hexdigest()

    return MaterializedFixture(
        fixture_id=fixture_id,
        repository_revision=repository_revision,
        task_fingerprint=task_fingerprint,
        evaluator_payload=evaluator_payload,
    )
