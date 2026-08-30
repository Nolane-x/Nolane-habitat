from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from habitat.compiler import compile_cache_fingerprint, compile_file
from habitat.semantic.tree_sitter_provider import TreeSitterProvider


Identity = tuple[str, str]


_FIXTURES: dict[str, dict[str, object]] = {
    "python": {
        "filename": "semantic_case.py",
        "source": (
            "class Greeter:\n"
            "    def greet(self, name):\n"
            "        return name\n\n"
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        "expected": {
            ("Greeter", "class"),
            ("Greeter.greet", "method"),
            ("add", "function"),
        },
    },
    "typescript": {
        "filename": "semantic_case.ts",
        "source": (
            "interface Named { name: string }\n"
            "class Greeter {\n"
            "  greet(name: string): string { return name; }\n"
            "}\n"
            "function add(a: number, b: number): number { return a + b; }\n"
        ),
        "expected": {
            ("Named", "interface"),
            ("Greeter", "class"),
            ("Greeter.greet", "method"),
            ("add", "function"),
        },
    },
}


def _identity_rows(values: set[Identity]) -> list[list[str]]:
    return [[qualified_name, kind] for qualified_name, kind in sorted(values)]


def measure_identities(
    expected: set[Identity],
    observed: set[Identity] | None,
    *,
    provider_id: str,
    provider_fingerprint: str | None,
    unavailable_reason: str | None = None,
) -> dict:
    """Measure exact declaration identities without inventing missing values."""
    expected_set = set(expected)
    if observed is None:
        return {
            "provider_id": provider_id,
            "provider_fingerprint": provider_fingerprint,
            "available": False,
            "reason": unavailable_reason or "provider unavailable",
            "expected_count": len(expected_set),
            "observed_count": None,
            "true_positive": None,
            "false_positive": None,
            "false_negative": None,
            "precision": None,
            "recall": None,
            "expected": _identity_rows(expected_set),
            "observed": None,
        }

    observed_set = set(observed)
    true_positive = len(expected_set & observed_set)
    false_positive = len(observed_set - expected_set)
    false_negative = len(expected_set - observed_set)
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    precision = (
        true_positive / precision_denominator
        if precision_denominator
        else (1.0 if not expected_set else 0.0)
    )
    recall = true_positive / recall_denominator if recall_denominator else 1.0
    return {
        "provider_id": provider_id,
        "provider_fingerprint": provider_fingerprint,
        "available": True,
        "reason": None,
        "expected_count": len(expected_set),
        "observed_count": len(observed_set),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "expected": _identity_rows(expected_set),
        "observed": _identity_rows(observed_set),
    }


def _symbol_identities(symbols) -> set[Identity]:
    return {
        (str(symbol.qualified_name), str(symbol.kind))
        for symbol in symbols
        if getattr(symbol, "qualified_name", None) and getattr(symbol, "kind", None)
    }


def _compiler_measurement(root: Path, path: Path, language: str, expected: set[Identity]) -> dict:
    compiled = compile_file(root, path)
    fingerprint = json.dumps(
        {
            "provider": compiled.provider,
            "python": f"{platform.python_implementation()}-{platform.python_version()}",
            "compiler_cache": compile_cache_fingerprint(language),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    measurement = measure_identities(
        expected,
        _symbol_identities(compiled.symbols),
        provider_id=compiled.provider,
        provider_fingerprint=fingerprint,
    )
    measurement["lane"] = "habitat-compiler"
    return measurement


def _tree_sitter_measurement(
    provider: TreeSitterProvider,
    root: Path,
    path: Path,
    language: str,
    expected: set[Identity],
) -> dict:
    available, reason = provider.available()
    fingerprint = provider.provider_fingerprint()
    if not available or language not in provider.languages:
        measurement = measure_identities(
            expected,
            None,
            provider_id=provider.id,
            provider_fingerprint=fingerprint,
            unavailable_reason=(
                reason if not available else f"Tree-sitter grammar unavailable for {language}"
            ),
        )
        measurement["lane"] = "tree-sitter"
        return measurement

    text = path.read_text(encoding="utf-8")
    result = provider.parse(root, path, text, f"fixture:{language}")
    if not result.available:
        measurement = measure_identities(
            expected,
            None,
            provider_id=provider.id,
            provider_fingerprint=fingerprint,
            unavailable_reason=result.reason or reason,
        )
    else:
        measurement = measure_identities(
            expected,
            _symbol_identities(result.symbols),
            provider_id=provider.id,
            provider_fingerprint=fingerprint,
        )
    measurement["lane"] = "tree-sitter"
    return measurement


def _language_coverage_admissible(block: dict) -> bool:
    available = [item for item in block["measurements"] if item["available"]]
    return (
        len(available) >= 2
        and len({item["provider_id"] for item in available}) >= 2
        and all(item["precision"] is not None and item["recall"] is not None for item in available)
    )


def build_report() -> dict:
    """Run the deterministic Foundation Convergence semantic precision matrix."""
    languages: dict[str, dict] = {}
    tree_sitter = TreeSitterProvider()
    with tempfile.TemporaryDirectory(prefix="habitat-semantic-precision-") as td:
        root = Path(td)
        for language, fixture in _FIXTURES.items():
            filename = str(fixture["filename"])
            source = str(fixture["source"])
            expected = set(fixture["expected"])
            path = root / filename
            path.write_text(source, encoding="utf-8")
            block = {
                "fixture": filename,
                "expected_count": len(expected),
                "expected": _identity_rows(expected),
                "measurements": [
                    _compiler_measurement(root, path, language, expected),
                    _tree_sitter_measurement(tree_sitter, root, path, language, expected),
                ],
            }
            block["coverage_admissible"] = _language_coverage_admissible(block)
            languages[language] = block

    coverage_admissible = (
        len(languages) >= 2
        and all(block["coverage_admissible"] for block in languages.values())
    )
    return {
        "schema": "nolane-semantic-precision-matrix-v1",
        "languages": languages,
        "coverage_requirements": {
            "minimum_languages": 2,
            "minimum_available_providers_per_language": 2,
            "distinct_provider_identity_required": True,
            "precision_recall_required_for_available_cells": True,
        },
        "coverage_admissible": coverage_admissible,
        "claim_boundary": (
            "Descriptive declaration-identity semantic precision/recall evidence only. "
            "It is not a universal semantic-correctness, coding-success, performance, or superiority claim."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    report = build_report()
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0 if report["coverage_admissible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
