#!/usr/bin/env python3
"""Controlled same-model A/B orchestration harness for Habitat.

Alpha.10 adds independent-evaluator support, diff fingerprints and paired summaries. The harness still
contains no model and never treats agent self-report as sufficient evidence when an evaluator is used.
"""
from __future__ import annotations

import argparse, hashlib, json, os, random, shlex, shutil, subprocess, tempfile, time
from pathlib import Path

REQUIRED_RESULT={"success":bool,"task_id":str,"tool_calls":int,"input_tokens":int,"output_tokens":int,"wall_ms":int}


def load_suite(path: Path):
    value=json.loads(path.read_text(encoding="utf-8")); tasks=value.get("tasks") if isinstance(value,dict) else None
    if not isinstance(tasks,list) or not tasks: raise ValueError("suite requires non-empty tasks array")
    for t in tasks:
        if not isinstance(t,dict) or not isinstance(t.get("id"),str) or not isinstance(t.get("repo"),str) or not isinstance(t.get("prompt"),str):
            raise ValueError("each task requires id/repo/prompt strings")
    return value


def clone_repo(src: Path, dst: Path):
    if not src.is_dir(): raise FileNotFoundError(src)
    shutil.copytree(src,dst,symlinks=True)


def git_diff_fingerprint(repo: Path) -> dict:
    try:
        p=subprocess.run(["git","-C",str(repo),"diff","--binary","--no-ext-diff"],capture_output=True,timeout=15,shell=False)
        raw=p.stdout if p.returncode==0 else b""
        names=subprocess.run(["git","-C",str(repo),"status","--porcelain=v1"],capture_output=True,text=True,timeout=10,shell=False)
        changed=[line[3:] for line in names.stdout.splitlines() if len(line)>=4] if names.returncode==0 else []
    except Exception:
        raw=b""; changed=[]
    return {"diff_sha256":hashlib.sha256(raw).hexdigest(),"diff_bytes":len(raw),"changed_paths":changed}


def command_args(command: str) -> list[str]:
    """Split an agent command without treating Windows path separators as escapes."""
    if not command.strip():
        raise ValueError("command must not be empty")
    if os.name != "nt":
        return shlex.split(command)
    return [arg[1:-1] if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in "\\\"'" else arg
            for arg in shlex.split(command, posix=False)]


def run_agent(command: str, task: dict, repo: Path, arm: str, timeout_s: int) -> dict:
    env=os.environ.copy(); env.update({"HABITAT_AB_ARM":arm,"HABITAT_AB_REPO":str(repo),"HABITAT_AB_TASK_ID":task["id"]})
    payload={"task_id":task["id"],"prompt":task["prompt"],"repo":str(repo),"arm":arm,"budget":task.get("budget") or {}}
    started=time.monotonic()
    p=subprocess.run(command_args(command),input=json.dumps(payload),text=True,capture_output=True,timeout=timeout_s,env=env,cwd=repo,shell=False)
    elapsed=int((time.monotonic()-started)*1000)
    if p.returncode!=0: return {"task_id":task["id"],"success":False,"agent_claimed_success":False,"harness_error":"agent-command-failed","returncode":p.returncode,"stderr":p.stderr[-4000:],"wall_ms":elapsed,**git_diff_fingerprint(repo)}
    try: result=json.loads(p.stdout)
    except Exception as exc: return {"task_id":task["id"],"success":False,"agent_claimed_success":False,"harness_error":f"invalid-json-result:{exc}","stdout":p.stdout[-4000:],"wall_ms":elapsed,**git_diff_fingerprint(repo)}
    for key,typ in REQUIRED_RESULT.items():
        if key not in result or not isinstance(result[key],typ) or (isinstance(result[key],bool) and typ is int): raise ValueError(f"agent result missing/invalid {key}")
    result["agent_claimed_success"]=bool(result["success"]); result["observed_wall_ms"]=elapsed; result["arm"]=arm
    result.update(git_diff_fingerprint(repo)); return result


def run_evaluator(command: str, task: dict, repo: Path, agent_result: dict, timeout_s: int) -> dict:
    payload={"task_id":task["id"],"prompt":task["prompt"],"repo":str(repo),"agent_result":agent_result,"evaluator":task.get("evaluator") or {}}
    p=subprocess.run(command_args(command),input=json.dumps(payload),text=True,capture_output=True,timeout=timeout_s,cwd=repo,shell=False)
    if p.returncode!=0: return {"ok":False,"success":False,"error":"evaluator-command-failed","returncode":p.returncode,"stderr":p.stderr[-4000:]}
    try: value=json.loads(p.stdout)
    except Exception as exc: return {"ok":False,"success":False,"error":f"invalid-evaluator-json:{exc}"}
    if not isinstance(value,dict) or not isinstance(value.get("success"),bool): raise ValueError("evaluator result requires boolean success")
    return {"ok":True,**value}


def paired_summary(runs: list[dict]) -> dict:
    by={}
    for r in runs: by.setdefault((r.get("task_id"),r.get("repetition")),{})[r.get("arm")]=r
    pairs=[]
    for key,arms in sorted(by.items()):
        if "filesystem" not in arms or "habitat" not in arms: continue
        a,b=arms["filesystem"],arms["habitat"]
        pairs.append({"task_id":key[0],"repetition":key[1],"filesystem_success":bool(a.get("success")),"habitat_success":bool(b.get("success")),
                      "success_delta":int(bool(b.get("success")))-int(bool(a.get("success"))),
                      "input_token_delta":int(b.get("input_tokens",0))-int(a.get("input_tokens",0)),
                      "tool_call_delta":int(b.get("tool_calls",0))-int(a.get("tool_calls",0)),
                      "wall_ms_delta":int(b.get("observed_wall_ms",b.get("wall_ms",0)))-int(a.get("observed_wall_ms",a.get("wall_ms",0)))})
    n=len(pairs)
    return {"pair_count":n,"pairs":pairs,"habitat_success_wins":sum(1 for x in pairs if x["success_delta"]>0),"filesystem_success_wins":sum(1 for x in pairs if x["success_delta"]<0),"ties":sum(1 for x in pairs if x["success_delta"]==0),
            "mean_input_token_delta":round(sum(x["input_token_delta"] for x in pairs)/n,2) if n else None,
            "mean_tool_call_delta":round(sum(x["tool_call_delta"] for x in pairs)/n,2) if n else None,
            "mean_wall_ms_delta":round(sum(x["wall_ms_delta"] for x in pairs)/n,2) if n else None}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--suite",required=True); ap.add_argument("--baseline-cmd",required=True); ap.add_argument("--habitat-cmd",required=True)
    ap.add_argument("--evaluator-cmd"); ap.add_argument("--repetitions",type=int,default=3); ap.add_argument("--timeout",type=int,default=1800); ap.add_argument("--seed",type=int,default=10); ap.add_argument("--out",required=True)
    ap.add_argument("--strong-evidence",action="store_true"); ap.add_argument("--model-id"); ap.add_argument("--scaffold-id"); ap.add_argument("--evaluator-id"); ap.add_argument("--environment-fingerprint")
    args=ap.parse_args()
    if args.repetitions<1 or args.repetitions>50: raise ValueError("repetitions must be in [1,50]")
    if args.strong_evidence:
        if args.repetitions<3: ap.error("strong evidence requires at least 3 repetitions")
        for option,value in (("--model-id",args.model_id),("--scaffold-id",args.scaffold_id),("--evaluator-id",args.evaluator_id),("--environment-fingerprint",args.environment_fingerprint),("--evaluator-cmd",args.evaluator_cmd)):
            if not isinstance(value,str) or not value.strip(): ap.error(f"{option} is required in strong evidence mode")
    suite=load_suite(Path(args.suite)); rng=random.Random(args.seed); runs=[]
    with tempfile.TemporaryDirectory(prefix="habitat-ab-") as td:
        base=Path(td)
        for rep in range(args.repetitions):
            for task in suite["tasks"]:
                arms=[("filesystem",args.baseline_cmd),("habitat",args.habitat_cmd)]; rng.shuffle(arms)
                for arm,cmd in arms:
                    repo=base/f"r{rep}-{task['id']}-{arm}"; clone_repo(Path(task["repo"]).resolve(),repo)
                    result=run_agent(cmd,task,repo,arm,args.timeout); result["repetition"]=rep
                    if args.evaluator_cmd:
                        ev=run_evaluator(args.evaluator_cmd,task,repo,result,args.timeout); result["evaluation"]=ev; result["success"]=bool(ev.get("success"))
                    runs.append(result)
    model_ids=sorted({str(r.get("model_id")) for r in runs if r.get("model_id") is not None}); scaffold_ids=sorted({str(r.get("scaffold_id")) for r in runs if r.get("scaffold_id") is not None})
    all_model_ids_present=all(isinstance(r.get("model_id"),str) and bool(r.get("model_id")) for r in runs)
    all_scaffold_ids_present=all(isinstance(r.get("scaffold_id"),str) and bool(r.get("scaffold_id")) for r in runs)
    same_model_observed=bool(runs) and all_model_ids_present and len(model_ids)==1
    same_scaffold_observed=bool(runs) and all_scaffold_ids_present and len(scaffold_ids)==1
    independent=bool(args.evaluator_cmd)
    reasons=[]
    if not same_model_observed: reasons.append("model identity missing or inconsistent across arms/runs")
    if not same_scaffold_observed: reasons.append("scaffold identity missing or inconsistent across arms/runs")
    if not independent: reasons.append("independent evaluator not configured")
    comparability={"same_model_observed":same_model_observed,"same_scaffold_observed":same_scaffold_observed,
                   "independent_evaluator":independent,"strong_evidence_ready":same_model_observed and same_scaffold_observed and independent,
                   "reasons":reasons}
    report={"schema":3,"same_model_required":True,"same_scaffold_required":True,"seed":args.seed,"repetitions":args.repetitions,"tasks":len(suite["tasks"]),"runs":runs,
            "evaluator_required_for_strong_evidence":True,"independent_evaluator_used":independent,"observed_model_ids":model_ids,"observed_scaffold_ids":scaffold_ids,
            "comparability":comparability,"paired_summary":paired_summary(runs),
            "claim_boundary":"This harness standardizes paired execution and accounting. Strong evidence is admitted only when every run reports one consistent model_id and scaffold_id and an independent evaluator is configured; agent self-reported success alone is never sufficient."}
    Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True),encoding="utf-8"); print(json.dumps({"out":args.out,"runs":len(runs),"pairs":report["paired_summary"]["pair_count"]},sort_keys=True))
if __name__=="__main__": main()
