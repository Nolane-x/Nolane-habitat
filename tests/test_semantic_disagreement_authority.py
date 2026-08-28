from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from habitat.model import SymbolRecord
from habitat.mutation import TransactionConflict
from habitat.semantic.admission import SemanticAdmissionRegistry
from habitat.semantic.base import SemanticParseResult, SemanticProvider
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


class _AuthorityProvider(SemanticProvider):
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

    def available(self):
        return True, "authority fixture"

    def provider_fingerprint(self):
        return f"authority-fixture:{self.id}"

    def parse(self, root: Path, path: Path, text: str, file_id: str):
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
                    signature="function foo(): void",
                    trust="semantic",
                )
            ],
        )


def _registry(*providers: _AuthorityProvider) -> SemanticAdmissionRegistry:
    registry = SemanticAdmissionRegistry()
    for provider in providers:
        registry.register(provider)
        registry.probe(provider.id)
        registry.admit(provider.id, evidence=(f"authority:{provider.id}",))
    return registry


class SemanticDisagreementAuthorityTests(unittest.TestCase):
    def test_disagreement_evidence_never_becomes_source_mutation_authority(self):
        with WorkspaceTemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            target = source / "a.ts"
            original = "export function foo(): void {}\n"
            target.write_text(original, encoding="utf-8")
            ws = HabitatWorkspace.create(source, root / "habitat")

            first = _AuthorityProvider("provider.a", "function")
            second = _AuthorityProvider("provider.b", "method")
            ws.semantic_registry = _registry(first, second)
            report = ws.semantic_disagreements(Path("a.ts"))

            self.assertGreater(report["claim_count"], 0)
            self.assertGreater(report["disagreement_count"], 0)
            self.assertTrue(all(claim.trust == "semantic" for claim in report["claims"]))
            self.assertTrue(all(item.resolution == "unresolved" for item in report["disagreements"]))
            # Wave 1 keeps comparison evidence call-local; it never creates a persisted source anchor.
            self.assertTrue(all(ws.store.symbol_by_id(claim.id) is None for claim in report["claims"]))
            self.assertNotIn("claims", ws._semantic_disagreement_state or {})
            self.assertNotIn("disagreements", ws._semantic_disagreement_state or {})

            # Even if a semantic-derived identity reaches the existing mutation boundary, trust is
            # still not action authority and replacement must fail before source transaction work.
            with mock.patch.object(
                ws.store,
                "symbol_by_id",
                return_value={"id": "semantic-disagreement", "trust": "semantic"},
            ):
                with self.assertRaises(TransactionConflict):
                    ws.stage_change(
                        [
                            {
                                "op": "replace_symbol_source",
                                "symbol_id": "semantic-disagreement",
                                "replacement": "export function foo(): number { return 1 }\n",
                            }
                        ]
                    )

            self.assertEqual(target.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
