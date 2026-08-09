import tempfile
import tomllib
import unittest
from pathlib import Path

from habitat.workspace import HabitatWorkspace
from habitat.semantic.python_jedi import probe


class PythonJediSemanticTests(unittest.TestCase):
    def test_dev_extra_includes_python_semantic_provider(self):
        config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        dependencies = config["project"]["optional-dependencies"]["dev"]
        self.assertIn("jedi>=0.19,<1", dependencies)
        self.assertIn("pytest>=8", dependencies)

    def test_cross_file_alias_call_resolves_to_exact_project_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"project"; root.mkdir()
            (root/"auth.py").write_text("def validate_credentials(value):\n    return bool(value)\n", encoding="utf-8")
            (root/"other.py").write_text("def validate_credentials(value):\n    return False\n", encoding="utf-8")
            (root/"service.py").write_text("from auth import validate_credentials as check\n\ndef login(value):\n    return check(value)\n", encoding="utf-8")
            ws=HabitatWorkspace.create(root, Path(td)/"ws")
            try:
                report=ws.semantic_provider_report()
                ok,_,_=probe()
                if not ok:
                    self.assertFalse(report["providers"]["python-jedi"]["available"])
                    return
                auth=next(s for s in ws.store.all_symbols() if s["path"]=="auth.py" and s["name"]=="validate_credentials")
                other=next(s for s in ws.store.all_symbols() if s["path"]=="other.py" and s["name"]=="validate_credentials")
                login=next(s for s in ws.store.all_symbols() if s["path"]=="service.py" and s["name"]=="login")
                rels=[dict(r) for r in [r for r in ws.store.relations_for(login["id"]) if r["source_id"]==login["id"] and r["kind"]=="calls"]]
                self.assertTrue(any(r["target_id"]==auth["id"] and r["trust"]=="semantic" for r in rels), rels)
                self.assertFalse(any(r["target_id"]==other["id"] for r in rels), rels)
                occ=[dict(r) for r in ws.store.occurrences_from_source(login["id"])]
                self.assertTrue(any(r["provider"]=="python-jedi" and r["target_id"]==auth["id"] for r in occ), occ)
                self.assertTrue(report["providers"]["python-jedi"]["available"])
                self.assertGreaterEqual(report["providers"]["python-jedi"]["relations"],1)
            finally:
                ws.close()


    def test_precise_call_site_does_not_erase_other_unresolved_call_site(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"project"; root.mkdir()
            (root/"auth.py").write_text("def validate_credentials(value):\n    return bool(value)\n", encoding="utf-8")
            (root/"left.py").write_text("def ambiguous(value):\n    return value\n", encoding="utf-8")
            (root/"right.py").write_text("def ambiguous(value):\n    return value\n", encoding="utf-8")
            (root/"service.py").write_text("from auth import validate_credentials as check\n\ndef login(value):\n    check(value)\n    return ambiguous(value)\n", encoding="utf-8")
            ws=HabitatWorkspace.create(root, Path(td)/"ws")
            try:
                login=next(x for x in ws.store.all_symbols() if x["path"]=="service.py" and x["name"]=="login")
                symbols=list(ws.store.all_symbols())
                rels=[dict(r) for r in ws.store.relations_for(login["id"]) if r["source_id"]==login["id"] and r["kind"]=="calls"]
                self.assertTrue(any(r["trust"]=="semantic" and "jedi-resolved" in (r["evidence"] or "") for r in rels), rels)
                ambiguous_ids={x["id"] for x in symbols if x["name"]=="ambiguous"}
                self.assertTrue(any(r["target_id"] in ambiguous_ids for r in rels), rels)
            finally:
                ws.close()


    def test_jedi_precision_partitions_recompute_one_file_for_body_only_edit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"project"; root.mkdir()
            (root/"a.py").write_text("def a():\n    return 1\n",encoding="utf-8")
            (root/"b.py").write_text("from a import a\n\ndef b():\n    return a()\n",encoding="utf-8")
            (root/"c.py").write_text("def c():\n    return 3\n",encoding="utf-8")
            ws=HabitatWorkspace.create(root,Path(td)/"ws")
            try:
                warm=ws.refresh(reason="warm-jedi-partitions")
                report=warm["project_semantics"]["python-jedi"]
                if not report.get("available"):
                    self.skipTest("Jedi unavailable")
                self.assertEqual(report["partitions_recomputed"],0,report)
                self.assertEqual(report["partitions_reused"],3,report)
                (root/"a.py").write_text("def a():\n    return 2\n",encoding="utf-8")
                body=ws.refresh(reason="body-only")["project_semantics"]["python-jedi"]
                self.assertEqual(body["partitions_recomputed"],1,body)
                self.assertEqual(body["partitions_reused"],2,body)
                (root/"a.py").write_text("def a():\n    return 2\n\ndef public_api():\n    return 4\n",encoding="utf-8")
                surface=ws.refresh(reason="api-surface")["project_semantics"]["python-jedi"]
                self.assertEqual(surface["partitions_recomputed"],3,surface)
            finally:
                ws.close()

    def test_indexing_does_not_execute_python_module(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"project"; root.mkdir()
            marker=root/"EXECUTED"
            (root/"danger.py").write_text("from pathlib import Path\nPath('EXECUTED').write_text('bad')\n\ndef f():\n    return 1\n", encoding="utf-8")
            ws=HabitatWorkspace.create(root, Path(td)/"ws")
            try:
                self.assertFalse(marker.exists())
            finally:
                ws.close()

if __name__ == '__main__': unittest.main()
