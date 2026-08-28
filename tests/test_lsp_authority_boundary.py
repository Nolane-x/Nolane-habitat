from __future__ import annotations

import unittest
from pathlib import Path

from habitat.model import SymbolRecord
from habitat.mutation import TransactionConflict
from tests.support import WorkspaceTemporaryDirectory


class LspAuthorityBoundaryTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory):
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        (source / "sample.py").write_text(
            "def target():\n    return 1\n",
            encoding="utf-8",
        )
        return temp.create_workspace(source, root / "habitat"), source

    def test_exact_python_source_anchor_still_authorizes_symbol_mutation(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, _ = self.make_workspace(temp)
            symbol = next(item for item in ws.store.all_symbols() if item["name"] == "target")
            self.assertEqual(symbol["trust"], "exact")

            staged = ws.stage_symbol_change(
                symbol["id"],
                "def target():\n    return 2",
            )

            self.assertEqual(staged["status"], "staged")
            self.assertEqual(staged["operations"][0]["symbol_trust"], "exact")

    def test_semantic_evidence_cannot_authorize_replace_symbol_source(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, _ = self.make_workspace(temp)
            exact = next(item for item in ws.store.all_symbols() if item["name"] == "target")
            semantic = SymbolRecord(
                id=exact["id"],
                file_id=exact["file_id"],
                path=exact["path"],
                name=exact["name"],
                qualified_name=exact["qualified_name"],
                kind=exact["kind"],
                language=exact["language"],
                start_line=exact["start_line"],
                end_line=exact["end_line"],
                signature=exact["signature"],
                summary=exact["summary"],
                trust="semantic",
            )
            ws.store.replace_symbols_for_file(exact["file_id"], [semantic])
            observed = ws.store.symbol_by_id(exact["id"])
            self.assertIsNotNone(observed)
            self.assertEqual(observed["trust"], "semantic")

            with self.assertRaises(TransactionConflict):
                ws.stage_symbol_change(
                    exact["id"],
                    "def target():\n    return 999",
                )


if __name__ == "__main__":
    unittest.main()
