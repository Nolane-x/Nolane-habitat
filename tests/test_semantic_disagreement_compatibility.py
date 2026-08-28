from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from habitat.model import SymbolRecord
from habitat.semantic.admission import SemanticAdmissionRegistry
from habitat.semantic.base import SemanticParseResult, SemanticProvider
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


class _CompatibilityProvider(SemanticProvider):
    layer = "test-semantic"
    trust_ceiling = "semantic"
    capabilities = frozenset({"parse"})
    lifecycle = "stateless"
    source_authority = False
    mutation_authority = False
    provenance_required = True

    def __init__(self, provider_id: str, kind: str):
        self.id = provider_id
        self.languages = frozenset({"typescript"})
        self.kind = kind
        self.calls = 0

    def available(self):
        return True, "compatibility fixture"

    def provider_fingerprint(self):
        return f"compatibility-fixture:{self.id}"

    def parse(self, root: Path, path: Path, text: str, file_id: str):
        self.calls += 1
        return SemanticParseResult(
            provider=self.id,
            available=True,
            symbols=[
                SymbolRecord(
                    id=f"{self.id}-foo",
                    file_id=file_id,
                    path=path.relative_to(root).as_posix(),
                    name="foo",
                    qualified_name="foo",
                    kind=self.kind,
                    language="typescript",
                    start_line=1,
                    end_line=1,
                    signature=f"{self.kind} foo",
                    trust="semantic",
                )
            ],
        )


def _registry(*providers: _CompatibilityProvider) -> SemanticAdmissionRegistry:
    registry = SemanticAdmissionRegistry()
    for provider in providers:
        registry.register(provider)
        registry.probe(provider.id)
        registry.admit(provider.id, evidence=(f"compatibility:{provider.id}",))
    return registry


class SemanticDisagreementCompatibilityTests(unittest.TestCase):
    def test_create_open_and_refresh_never_auto_run_disagreement_comparison(self):
        with WorkspaceTemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            target = source / "a.ts"
            target.write_text("export function foo(): void {}\n", encoding="utf-8")
            habitat_dir = root / "habitat"

            with mock.patch("habitat.workspace.compare_parse_providers") as compare:
                ws = HabitatWorkspace.create(source, habitat_dir)
                ws.refresh(reason="compatibility-refresh")
                ws.close()

                reopened = HabitatWorkspace(habitat_dir)
                reopened.refresh(reason="compatibility-open-refresh")
                reopened.close()

            compare.assert_not_called()

    def test_primary_compile_precedence_is_unchanged_when_comparison_is_not_requested(self):
        with WorkspaceTemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            target = source / "a.ts"
            target.write_text("export function foo(): void {}\n", encoding="utf-8")
            ws = HabitatWorkspace.create(source, root / "habitat")

            first = _CompatibilityProvider("provider.a", "function")
            second = _CompatibilityProvider("provider.b", "method")
            ws.semantic_registry = _registry(first, second)
            target.write_text("export function foo(): void { return; }\n", encoding="utf-8")

            with mock.patch("habitat.workspace.compare_parse_providers") as compare:
                ws.refresh_paths(["a.ts"], reason="compatibility-primary-precedence")

            compare.assert_not_called()
            self.assertEqual((first.calls, second.calls), (1, 0))
            symbols = [item for item in ws.store.all_symbols() if item["path"] == "a.ts" and item["name"] == "foo"]
            self.assertEqual(len(symbols), 1)
            self.assertEqual(symbols[0]["kind"], "function")
            self.assertEqual(symbols[0]["trust"], "semantic")

    def test_explicit_comparison_does_not_change_provider_admission(self):
        with WorkspaceTemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "a.ts").write_text("export function foo(): void {}\n", encoding="utf-8")
            ws = HabitatWorkspace.create(source, root / "habitat")

            first = _CompatibilityProvider("provider.a", "function")
            second = _CompatibilityProvider("provider.b", "method")
            registry = _registry(first, second)
            ws.semantic_registry = registry
            before = registry.cache_identity("parse", language="typescript")

            ws.semantic_disagreements(Path("a.ts"))

            after = registry.cache_identity("parse", language="typescript")
            self.assertEqual(after, before)
            self.assertTrue(registry.is_admitted("provider.a"))
            self.assertTrue(registry.is_admitted("provider.b"))
            self.assertEqual((first.calls, second.calls), (1, 1))


if __name__ == "__main__":
    unittest.main()
