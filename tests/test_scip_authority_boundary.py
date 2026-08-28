from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from habitat.mutation import TransactionConflict
from habitat.workspace import HabitatWorkspace
from tests.scip_fixture import sample_index
from tests.support import WorkspaceTemporaryDirectory


class ScipAuthorityBoundaryTests(unittest.TestCase):
    def test_scip_semantic_evidence_cannot_authorize_source_replacement(self):
        with WorkspaceTemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "src").mkdir()
            (source / "src" / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            (source / "src" / "b.py").write_text("x = 1\n\nvalue = foo()\n", encoding="utf-8")
            payload, symbol = sample_index()
            index_path = root / "index.scip"
            index_path.write_bytes(payload)
            ws = HabitatWorkspace.create(source, root / "habitat")
            ws.scip_activate(index_path, provider_id="scip.fixture")

            evidence = ws.scip_definitions("scip.fixture", symbol)
            self.assertEqual(evidence["trust"], "semantic")
            self.assertFalse(ws._scip_manager()._providers["scip.fixture"].provider.descriptor().source_authority)
            self.assertFalse(ws._scip_manager()._providers["scip.fixture"].provider.descriptor().mutation_authority)

            # Mutation routing consults stored source anchors, not arbitrary semantic payloads. Even
            # if a SCIP-derived symbol identity reaches that boundary, semantic trust must remain
            # read-only and fail before the core transaction machinery is entered.
            with mock.patch.object(
                ws.store,
                "symbol_by_id",
                return_value={"id": "scip-symbol", "trust": "semantic"},
            ):
                with self.assertRaises(TransactionConflict) as caught:
                    ws.stage_change(
                        [
                            {
                                "op": "replace_symbol_source",
                                "symbol_id": "scip-symbol",
                                "replacement": "def foo():\n    return 2\n",
                            }
                        ]
                    )

            self.assertIn("read-only", str(caught.exception))
            self.assertEqual((source / "src" / "a.py").read_text(encoding="utf-8"), "def foo():\n    pass\n")


if __name__ == "__main__":
    unittest.main()
