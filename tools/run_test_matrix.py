#!/usr/bin/env python3
"""Process-isolated Habitat regression matrix.

Default mode uses empirically balanced process shards so optional language/browser providers are reused
inside a bounded process without coupling the whole historical suite. `--mode module` is a slower
forensic mode that isolates every test file. Reports never relabel timeout as pass.
"""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, os, re, signal, subprocess, sys, tempfile, time
from pathlib import Path
RAN=re.compile(r"Ran\s+(\d+)\s+tests?")

SHARDS={
 "alpha0-4":["test_adversarial","test_alpha1_protocol","test_alpha1_schema_contracts","test_alpha1_semantics","test_alpha2_schema_contracts","test_alpha2_semantic_loop","test_alpha3_live_workspace","test_alpha3_schema_contracts","test_alpha4_agent_residency","test_alpha4_schema_contracts"],
 "alpha5-7":["test_alpha5_deep_evolution","test_alpha5_schema_contracts","test_alpha6_backend_cognition","test_alpha6_schema_contracts","test_alpha7_deep_substrate","test_alpha7_schema_contracts"],
 "alpha8-10":["test_alpha8_integrity_cognition","test_alpha9_benchmark_harness","test_alpha9_policy_multiagent_git","test_alpha9_schema_contracts","test_alpha10_deep_evolution"],
 "alpha11-12":["test_alpha11_observatory_runtime","test_alpha12_cinematic_world","test_alpha12_observatory_cinematic"],
 "alpha13":["test_alpha13_microdepth_resilience"],
 "alpha14-17":["test_alpha14_executive_trajectory","test_alpha15_ai_operator","test_alpha16_forensic_nearlive","test_alpha17_stability_completion"],
 "core":["test_capabilities","test_compiler","test_execution","test_large_file_coverage","test_protocol","test_python_jedi","test_schemas","test_source_bridge","test_storage","test_workspace"],
}

def run_group(root: Path, name: str, modules: list[str], timeout: int) -> dict:
    qualified=["tests."+m for m in modules]; started=time.monotonic()
    try:
        return _run_group(root, name, qualified, timeout, started)
    except Exception as exc:
        return {"group":name,"modules":qualified,"status":"infra-error","returncode":None,"tests":None,"wall_ms":round((time.monotonic()-started)*1000,2),"error":f"{type(exc).__name__}: {exc}"}


def _run_group(root: Path, name: str, qualified: list[str], timeout: int, started: float) -> dict:
    # Do not capture through OS pipes: browser/Node/language-service descendants can inherit
    # those descriptors and keep communicate() waiting for EOF after unittest itself exits.
    with tempfile.TemporaryDirectory(prefix="habitat-test-matrix-") as td:
        out_path=Path(td)/"stdout.log"; err_path=Path(td)/"stderr.log"
        try:
            with out_path.open("w+",encoding="utf-8",errors="replace") as out, err_path.open("w+",encoding="utf-8",errors="replace") as err:
                p=subprocess.Popen([sys.executable,"-m","unittest","-q",*qualified],cwd=root,stdout=out,stderr=err,text=True,env={**os.environ,"PYTHONUNBUFFERED":"1"},shell=False,start_new_session=(os.name!="nt"))
                try:
                    rc=p.wait(timeout=timeout); status="passed" if rc==0 else "failed"
                except subprocess.TimeoutExpired:
                    status="timeout"; rc=None
                    try:
                        if os.name!="nt": os.killpg(p.pid, signal.SIGKILL)
                        else: p.kill()
                    except Exception:
                        try:p.kill()
                        except Exception:pass
                    try:p.wait(timeout=5)
                    except Exception:pass
                finally:
                    # A completed shard owns its process group. Any descendant still alive is a
                    # leaked provider/browser helper and must not contaminate the next shard.
                    if os.name!="nt":
                        try: os.killpg(p.pid, signal.SIGTERM)
                        except ProcessLookupError: pass
                        except Exception: pass
            stdout=out_path.read_text(encoding="utf-8",errors="replace") if out_path.exists() else ""
            stderr=err_path.read_text(encoding="utf-8",errors="replace") if err_path.exists() else ""
            elapsed=round((time.monotonic()-started)*1000,2); text=stdout+"\n"+stderr; m=RAN.search(text)
            return {"group":name,"modules":qualified,"status":status,"returncode":rc,"tests":int(m.group(1)) if m else None,"wall_ms":elapsed,"stdout_tail":stdout[-3000:],"stderr_tail":stderr[-6000:]}
        except Exception as exc:
            return {"group":name,"modules":qualified,"status":"infra-error","returncode":None,"tests":None,"wall_ms":round((time.monotonic()-started)*1000,2),"error":f"{type(exc).__name__}: {exc}"}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--mode',choices=['shard','module'],default='shard'); ap.add_argument('--workers',type=int,default=1); ap.add_argument('--timeout',type=int,default=180); ap.add_argument('--match'); ap.add_argument('--source-commit'); ap.add_argument('--out')
    args=ap.parse_args(); root=Path(__file__).resolve().parents[1]
    if args.workers<1 or args.workers>8: raise ValueError('workers must be in [1,8]')
    if args.timeout<5 or args.timeout>1800: raise ValueError('timeout must be in [5,1800]')
    if args.source_commit is not None and not re.fullmatch(r'[0-9a-f]{40}',args.source_commit): raise ValueError('source commit must be a 40-character lowercase SHA')
    if args.mode=='shard':
        groups=[(k,v) for k,v in SHARDS.items() if not args.match or args.match in k or any(args.match in x for x in v)]
    else:
        paths=sorted((root/'tests').glob('test_*.py')); groups=[(p.stem,[p.stem]) for p in paths if not args.match or args.match in p.stem]
    started=time.monotonic(); rows=[]
    if args.workers == 1:
        # Deterministic sequential mode avoids cross-thread subprocess lifecycle surprises and is
        # the admission default for provider/browser-heavy suites.
        for name,mods in groups:
            rows.append(run_group(root,name,mods,args.timeout))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs={ex.submit(run_group,root,name,mods,args.timeout):name for name,mods in groups}
            for f in concurrent.futures.as_completed(futs): rows.append(f.result())
    rows.sort(key=lambda x:x['group']); statuses={k:sum(r['status']==k for r in rows) for k in ('passed','failed','timeout','infra-error')}; known=sum(r['tests'] or 0 for r in rows)
    report={"schema":2,"mode":args.mode,"group_count":len(rows),"known_test_count":known,"statuses":statuses,"wall_ms":round((time.monotonic()-started)*1000,2),"groups":rows,
            "claim_boundary":"Default balanced-shard CI feedback. Every selected unittest module is executed, but a separate monolithic long-lived-host probe remains useful for lifecycle/pathological-state testing."}
    if args.source_commit is not None:
        report.update({"suite":"isolated-regression-matrix","source_commit":args.source_commit,"status":"passed" if not any(statuses[key] for key in ('failed','timeout','infra-error')) else "failed"})
        report["report_sha256"]=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    text=json.dumps(report,indent=2,sort_keys=True)
    if args.out:
        output=Path(args.out); output.parent.mkdir(parents=True,exist_ok=True)
        temporary=output.with_name(f".{output.name}.tmp")
        temporary.write_text(text,encoding='utf-8')
        temporary.replace(output)
    print(json.dumps({"mode":args.mode,"groups":len(rows),"known_tests":known,"statuses":statuses,"wall_ms":report['wall_ms']},sort_keys=True))
    if statuses['failed'] or statuses['timeout'] or statuses['infra-error']: raise SystemExit(1)
if __name__=='__main__': main()
