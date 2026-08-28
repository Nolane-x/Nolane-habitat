from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from habitat.model import SymbolRecord
from habitat.mutation import TransactionConflict
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


class TruthMutationAuthorityTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory):
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        (source / "sample.py").write_text(
            "def target():\n    return 1\n",
            encoding="utf-8",
        )
        ws = HabitatWorkspace.create(source, root / "habitat")
        symbol = next(item for item in ws.store.all_symbols() if item["name"] == "target")
        return ws, symbol

    def set_symbol_trust(self, ws: HabitatWorkspace, symbol, trust: str):
        replacement = SymbolRecord(
            id=symbol["id"],
            file_id=symbol["file_id"],
            path=symbol["path"],
            name=symbol["name"],
            qualified_name=symbol["qualified_name"],
            kind=symbol["kind"],
            language=symbol["language"],
            start_line=symbol["start_line"],
            end_line=symbol["end_line"],
            signature=symbol["signature"],
            summary=symbol["summary"],
            trust=trust,  # type: ignore[arg-type]
        )
        ws.store.replace_symbols_for_file(symbol["file_id"], [replacement])
        observed = ws.store.symbol_by_id(symbol["id"])
        self.assertIsNotNone(observed)
        return observed

    def test_exact_anchor_still_passes_into_existing_transaction_handling(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, symbol = self.make_workspace(temp)

            staged = ws.stage_symbol_change(symbol["id"], "def target():\n    return 2")

            self.assertEqual(staged["status"], "staged")
            self.assertEqual(staged["operations"][0]["symbol_trust"], "exact")

    def test_operation_authority_helper_is_the_enforcement_seam(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, symbol = self.make_workspace(temp)

            with patch(
                "habitat.services.transaction.operation_allows_evidence",
                return_value=False,
                create=True,
            ) as allows:
                with self.assertRaises(TransactionConflict):
                    ws.stage_symbol_change(symbol["id"], "def target():\n    return 3")

            allows.assert_called_once()
            self.assertEqual(allows.call_args.args[0], "replace_symbol_source")

    def test_authority_helper_can_delegate_a_non_exact_anchor_to_existing_transaction_checks(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, symbol = self.make_workspace(temp)
            semantic = self.set_symbol_trust(ws, symbol, "semantic")

            with patch(
                "habitat.services.transaction.operation_allows_evidence",
                return_value=True,
                create=True,
            ) as allows:
                staged = ws.stage_symbol_change(
                    semantic["id"],
                    "def target():\n    return 4",
                )

            allows.assert_called_once()
            self.assertEqual(staged["status"], "staged")

    def test_non_exact_and_unknown_anchors_preserve_transaction_conflict_boundary(self):
        expected_message = (
            "source mutation requires an exact source-authorized anchor; "
            "{trust} evidence is read-only and non-authoritative"
        )
        for trust in ("semantic", "parser", "heuristic", "derived", "unknown"):
            with self.subTest(trust=trust), WorkspaceTemporaryDirectory() as temp:
                ws, symbol = self.make_workspace(temp)
                weak = self.set_symbol_trust(ws, symbol, trust)

                with self.assertRaisesRegex(
                    TransactionConflict,
                    expected_message.format(trust=trust),
                ):
                    ws.stage_symbol_change(
                        weak["id"],
                        "def target():\n    return 5",
                    )

    def test_confidence_or_recalled_origin_metadata_cannot_promote_weak_anchor(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, symbol = self.make_workspace(temp)
            weak = self.set_symbol_trust(ws, symbol, "semantic")
            operation = {
                "op": "replace_symbol_source",
                "symbol_id": weak["id"],
                "source": "def target():\n    return 6",
                "confidence": 1.0,
                "origin_authority_class": "SOURCE_EXACT",
                "origin_claim_id": "remembered-source-claim",
            }

            with self.assertRaises(TransactionConflict):
                ws.stage_change([operation])


if __name__ == "__main__":
    unittest.main()
