from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from habitat.model import SymbolRecord
from habitat.semantic.admission import SemanticAdmissionRegistry
from habitat.semantic.base import SemanticParseResult, SemanticProvider


class _Provider(SemanticProvider):
    layer = "test-semantic"
    trust_ceiling = "semantic"
    capabilities = frozenset({"parse"})
    lifecycle = "stateless"
    source_authority = False
    mutation_authority = False
    provenance_required = True

    def __init__(self, provider_id: str, *, symbols=(), available: bool = True, error: Exception | None = None,
                 mutate=None, languages=frozenset({"typescript"})):
        self.id = provider_id
        self.languages = frozenset(languages)
        self._symbols = list(symbols)
        self._available = available
        self._error = error
        self._mutate = mutate
        self.calls = 0

    def available(self):
        return True, "fixture provider detected"

    def provider_fingerprint(self):
        return f"fixture:{self.id}"

    def parse(self, root: Path, path: Path, text: str, file_id: str):
        self.calls += 1
        if self._mutate is not None:
            self._mutate(path)
        if self._error is not None:
            raise self._error
        return SemanticParseResult(
            provider=self.id,
            available=self._available,
            symbols=list(self._symbols),
            reason="fixture unavailable" if not self._available else "",
        )


def _symbol(path: str = "a.ts", *, kind: str = "function", start: int = 1, end: int = 1,
            signature: str = "function foo(): void") -> SymbolRecord:
    return SymbolRecord(
        id=f"sym-{kind}-{start}-{signature}",
        file_id="file-a",
        path=path,
        name="foo",
        qualified_name="foo",
        kind=kind,
        language="typescript",
        start_line=start,
        end_line=end,
        signature=signature,
        trust="semantic",
    )


def _registry(*providers: tuple[_Provider, bool]) -> SemanticAdmissionRegistry:
    registry = SemanticAdmissionRegistry()
    for provider, admitted in providers:
        registry.register(provider)
        registry.probe(provider.id)
        if admitted:
            registry.admit(provider.id, evidence=(f"fixture:{provider.id}",))
    return registry


class SemanticComparisonTests(unittest.TestCase):
    def _source(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        path = root / "a.ts"
        path.write_text("export function foo(): void {}\n", encoding="utf-8")
        self.addCleanup(temp.cleanup)
        return root, path

    def test_agreeing_admitted_parse_providers_produce_complete_zero_conflict_report(self):
        from habitat.semantic.comparison import compare_parse_providers

        root, path = self._source()
        a = _Provider("provider.a", symbols=[_symbol()])
        b = _Provider("provider.b", symbols=[_symbol()])
        report = compare_parse_providers(root, path, _registry((a, True), (b, True)), "rev-1")

        self.assertTrue(report["comparison_complete"])
        self.assertEqual(report["provider_ids"], ["provider.a", "provider.b"])
        self.assertEqual(report["disagreement_count"], 0)
        self.assertEqual(report["claim_count"], 2)
        self.assertEqual({item["status"] for item in report["providers"]}, {"complete"})

    def test_kind_difference_for_same_qualified_symbol_is_attribute_conflict(self):
        from habitat.semantic.comparison import compare_parse_providers

        root, path = self._source()
        a = _Provider("provider.a", symbols=[_symbol(kind="function")])
        b = _Provider("provider.b", symbols=[_symbol(kind="method")])
        report = compare_parse_providers(root, path, _registry((a, True), (b, True)), "rev-1")

        self.assertEqual(report["disagreement_count"], 1)
        self.assertEqual(report["disagreements"][0].kind, "attribute-conflict")
        self.assertEqual(report["disagreements"][0].subject_key, "symbol:a.ts:foo")

    def test_provider_exception_makes_comparison_incomplete_without_false_presence_conflict(self):
        from habitat.semantic.comparison import compare_parse_providers

        root, path = self._source()
        a = _Provider("provider.a", symbols=[_symbol()])
        b = _Provider("provider.b", error=RuntimeError("fixture explosion"))
        report = compare_parse_providers(root, path, _registry((a, True), (b, True)), "rev-1")

        self.assertFalse(report["comparison_complete"])
        self.assertEqual(report["disagreement_count"], 0)
        failed = next(item for item in report["providers"] if item["provider_id"] == "provider.b")
        self.assertEqual(failed["status"], "error")
        self.assertIn("RuntimeError", failed["reason"])

    def test_unavailable_parse_result_is_incomplete_not_negative_evidence(self):
        from habitat.semantic.comparison import compare_parse_providers

        root, path = self._source()
        a = _Provider("provider.a", symbols=[_symbol()])
        b = _Provider("provider.b", available=False)
        report = compare_parse_providers(root, path, _registry((a, True), (b, True)), "rev-1")

        self.assertFalse(report["comparison_complete"])
        self.assertEqual(report["disagreement_count"], 0)
        unavailable = next(item for item in report["providers"] if item["provider_id"] == "provider.b")
        self.assertEqual(unavailable["status"], "unavailable")

    def test_unadmitted_provider_is_never_executed(self):
        from habitat.semantic.comparison import compare_parse_providers

        root, path = self._source()
        a = _Provider("provider.a", symbols=[_symbol()])
        b = _Provider("provider.b", symbols=[_symbol()])
        hidden = _Provider("provider.hidden", error=AssertionError("must not execute"))
        report = compare_parse_providers(
            root, path, _registry((a, True), (hidden, False), (b, True)), "rev-1"
        )

        self.assertEqual(hidden.calls, 0)
        self.assertEqual(report["provider_ids"], ["provider.a", "provider.b"])
        self.assertTrue(report["comparison_complete"])

    def test_provider_bound_is_explicit_and_deterministic(self):
        from habitat.semantic.comparison import compare_parse_providers

        root, path = self._source()
        providers = [_Provider(f"provider.{index}", symbols=[_symbol()]) for index in range(5)]
        registry = _registry(*[(provider, True) for provider in providers])
        report = compare_parse_providers(root, path, registry, "rev-1", max_providers=2)

        self.assertEqual(report["provider_ids"], ["provider.0", "provider.1"])
        self.assertTrue(report["provider_truncated"])
        self.assertEqual([provider.calls for provider in providers], [1, 1, 0, 0, 0])

    def test_claim_truncation_suppresses_negative_space(self):
        from habitat.semantic.comparison import compare_parse_providers

        root, path = self._source()
        symbols = [
            SymbolRecord(
                id=f"sym-{index}", file_id="file-a", path="a.ts", name=f"f{index}",
                qualified_name=f"f{index}", kind="function", language="typescript",
                start_line=index + 1, end_line=index + 1, signature=f"function f{index}()", trust="semantic"
            )
            for index in range(3)
        ]
        a = _Provider("provider.a", symbols=symbols)
        b = _Provider("provider.b", symbols=[])
        report = compare_parse_providers(
            root, path, _registry((a, True), (b, True)), "rev-1", max_claims=1
        )

        self.assertTrue(report["claim_truncated"])
        self.assertTrue(report["truncated"])
        self.assertFalse(report["comparison_complete"])
        self.assertEqual(report["disagreement_count"], 0)

    def test_source_digest_drift_rejects_mixed_snapshot(self):
        from habitat.semantic.comparison import SemanticComparisonStaleError, compare_parse_providers

        root, path = self._source()
        a = _Provider("provider.a", symbols=[_symbol()])
        b = _Provider("provider.b", symbols=[_symbol()], mutate=lambda target: target.write_text("changed\n", encoding="utf-8"))
        with self.assertRaises(SemanticComparisonStaleError):
            compare_parse_providers(root, path, _registry((a, True), (b, True)), "rev-1")

    def test_revision_drift_rejects_mixed_snapshot(self):
        from habitat.semantic.comparison import SemanticComparisonStaleError, compare_parse_providers

        root, path = self._source()
        current = ["rev-1"]
        a = _Provider("provider.a", symbols=[_symbol()])
        b = _Provider("provider.b", symbols=[_symbol()], mutate=lambda _target: current.__setitem__(0, "rev-2"))
        with self.assertRaises(SemanticComparisonStaleError):
            compare_parse_providers(
                root, path, _registry((a, True), (b, True)), "rev-1",
                revision_getter=lambda: current[0],
            )


if __name__ == "__main__":
    unittest.main()
