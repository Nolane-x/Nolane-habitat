from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace


def build(root: Path) -> None:
    (root / "tests").mkdir(parents=True)
    (root / "auth.py").write_text(
        'def validate_credentials(user, password):\n'
        '    return user == "admin" and password == "secret"\n\n'
        'def login(user, password):\n'
        '    return validate_credentials(user, password)\n', encoding="utf-8")
    (root / "tests" / "test_auth.py").write_text(
        'import unittest\nfrom auth import validate_credentials\n\n'
        'class T(unittest.TestCase):\n'
        '    def test_valid(self):\n'
        '        self.assertTrue(validate_credentials("admin", "secret"))\n', encoding="utf-8")


def semantic_signature(ws: HabitatWorkspace) -> dict:
    symbols = sorted((s["path"], s["qualified_name"], s["kind"], s["trust"]) for s in ws.store.all_symbols())
    relations = sorted((r["source_id"], r["target_id"], r["kind"], r["trust"]) for r in ws.store.conn.execute("SELECT source_id,target_id,kind,trust FROM relations"))
    occurrences = sorted((r["path"], r["start_line"], r["start_column"], r["role"], r["target_id"] or "") for r in ws.store.conn.execute("SELECT path,start_line,start_column,role,target_id FROM occurrences"))
    return {"symbols": symbols, "relations": relations, "occurrences": occurrences}


def run_case(root: Path, backend: str) -> dict:
    h = root.parent / f"habitat-{backend}"
    with HabitatWorkspace.create(root, h, backend=backend) as ws:
        before = semantic_signature(ws)
        ctx = ws.orient("fix credential validation login", 8)
        target = next(s for s in ws.store.all_symbols() if s["path"] == "auth.py" and s["name"] == "validate_credentials")
        body = ws.inspect(target["id"], "body")["source"]
        tx = ws.stage_symbol_change(target["id"], body.replace('password == "secret"', 'password in {"secret", "backup"}'))
        commit = ws.commit_change(tx["id"])
        verify = ws.verify(changed_paths=commit["changed_paths"], timeout_s=30)
        after = semantic_signature(ws)
        return {
            "backend": ws.backend_info(),
            "before": before,
            "after": after,
            "context_paths": [x.path for x in ctx.objects],
            "context_confidence": ctx.decision_packet.get("retrieval_confidence"),
            "canonical_auth": ws.read_source_bytes("auth.py").decode("utf-8"),
            "verification": verify["receipt"],
        }


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--output"); args = ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        seed = base / "seed"; seed.mkdir(); build(seed)
        local_project = base / "local-project"; mirror_project = base / "mirror-project"
        shutil.copytree(seed, local_project); shutil.copytree(seed, mirror_project)
        local = run_case(local_project, "local")
        mirror = run_case(mirror_project, "mirror")
        report = {
            "release": "0.1.0-alpha.6",
            "semantic_before_equal": local["before"] == mirror["before"],
            "semantic_after_equal": local["after"] == mirror["after"],
            "context_paths_equal": local["context_paths"] == mirror["context_paths"],
            "context_confidence_equal": local["context_confidence"] == mirror["context_confidence"],
            "canonical_source_equal_after_mutation": local["canonical_auth"] == mirror["canonical_auth"],
            "local_execution_provenance": {
                "backend_id": local["verification"].get("backend_id"),
                "execution_backend": local["verification"].get("execution_backend"),
            },
            "mirror_execution_provenance": {
                "backend_id": mirror["verification"].get("backend_id"),
                "execution_backend": mirror["verification"].get("execution_backend"),
            },
            "verification_equal": local["verification"]["exit_code"] == mirror["verification"]["exit_code"] == 0,
            "claim_boundary": (
                "This is a local contract-double equivalence test. It proves Habitat semantic behavior is backend-separated "
                "for these fixtures; it is not a Cloudflare Computer integration test."
            ),
        }
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.output: Path(args.output).write_text(text, encoding="utf-8")
    else: print(text)


if __name__ == "__main__": main()
