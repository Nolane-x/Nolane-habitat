from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from habitat.workspace import HabitatWorkspace


def build(root: Path) -> None:
    (root / "tests").mkdir(parents=True)
    (root / "auth.py").write_text(
        'def validate_credentials(user, password):\n'
        '    """credential validation login"""\n'
        '    return user == "admin" and password == "secret"\n\n'
        'def login(user, password):\n'
        '    return validate_credentials(user, password)\n',
        encoding="utf-8",
    )
    (root / "billing.py").write_text(
        'def calculate_invoice_tax(amount, rate):\n'
        '    """invoice tax billing"""\n'
        '    return amount * rate\n', encoding="utf-8")
    (root / "tests" / "test_auth.py").write_text(
        'import unittest\nfrom auth import validate_credentials\n\n'
        'class AuthTest(unittest.TestCase):\n'
        '    def test_valid(self):\n'
        '        self.assertTrue(validate_credentials("admin", "secret"))\n', encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        project = base / "project"
        project.mkdir()
        build(project)
        started = time.perf_counter()
        ws = HabitatWorkspace.create(project, base / "habitat", backend="mirror")
        cold_ms = round((time.perf_counter() - started) * 1000, 2)
        info = ws.backend_info()

        ctx = ws.orient("change credential validation login and verify", 10)
        plan = ws.context_plan_next(ctx.handle, max_pages=2, max_estimated_bytes=5000)
        fetched = ws.context_fetch_pages(ctx.handle, plan.get("page_ids", []), 5000)
        target = next(s for s in ws.store.all_symbols() if s["path"] == "auth.py" and s["name"] == "validate_credentials")
        feedback = ws.context_feedback(ctx.handle, [target["id"]], [], 1.0)
        followup = ws.orient("review credential validation login", 10)
        followup_record = ws.store.load_json("context_slices", followup.handle)
        target_followup = next(x for x in followup_record["ranked"] if x["object_id"] == target["id"])

        episode = ws.episode_start("change credential validation and verify", ctx.handle)
        body = ws.inspect(target["id"], "body")["source"]
        tx = ws.stage_symbol_change(
            target["id"], body.replace('password == "secret"', 'password in {"secret", "backup"}'), episode["id"]
        )
        commit = ws.commit_change(tx["id"])
        verification = ws.verify(changed_paths=commit["changed_paths"], timeout_s=30, episode_id=episode["id"])
        final_episode = ws.episode_finish(episode["id"], "completed", {"verification": "passed"})
        causal = ws.causality_explain(tx["id"])

        checkpoint = ws.checkpoint("continue credential hardening", next_action="review verification evidence")
        resume = ws.resume(checkpoint["id"])
        no_gold = ws.orient("quantum banana teleportation matrix", 8)
        no_gold_plan = ws.context_plan_next(no_gold.handle, max_pages=3, max_estimated_bytes=5000)
        warm = ws.refresh("alpha6-demo-warm")

        authority = Path(info["authoritative_root"])
        mirror = Path(info["materialized_root"])
        authority_bytes = (authority / "auth.py").read_bytes()
        mirror_bytes = (mirror / "auth.py").read_bytes()
        receipt = verification["receipt"]
        report = {
            "release": "0.1.0-alpha.6",
            "cold_ingest_ms": cold_ms,
            "backend": info,
            "context": {
                "confidence": ctx.decision_packet.get("retrieval_confidence"),
                "planned_pages": plan.get("page_ids", []),
                "exact_source_bytes": fetched.get("source_bytes", 0),
                "feedback": feedback,
                "followup_target_lanes": target_followup.get("lane", []),
                "followup_target_score": target_followup.get("score"),
            },
            "episode": {
                "id": episode["id"],
                "status": final_episode["status"],
                "link_kinds": [x["kind"] for x in final_episode["links"]],
                "causality_episode_count": causal["episode_count"],
            },
            "mutation": {
                "changed_paths": commit["changed_paths"],
                "authority_mirror_equal": authority_bytes == mirror_bytes,
                "authority_contains_backup": b'"backup"' in authority_bytes,
            },
            "verification": {
                "status": (receipt.get("structured") or {}).get("status"),
                "exit_code": receipt["exit_code"],
                "backend_id": receipt.get("backend_id"),
                "execution_backend": receipt.get("execution_backend"),
            },
            "checkpoint_resume": {
                "mode": resume.get("resume_mode"),
                "backend_identity_drift": resume.get("backend_identity_drift"),
            },
            "selective_retrieval": {
                "no_gold_confidence": no_gold.decision_packet.get("retrieval_confidence"),
                "abstention_recommended": no_gold.decision_packet.get("abstention_recommended"),
                "page_plan_action": no_gold_plan.get("action"),
                "source_bytes_read": no_gold_plan.get("source_bytes_read"),
            },
            "warm_refresh": warm,
            "claim_boundary": (
                "Executable alpha.6 backend/cognition plumbing demo. It does not establish model token savings, "
                "coding superiority, Cloudflare compatibility, or AGI capability."
            ),
        }
        ws.close()
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
