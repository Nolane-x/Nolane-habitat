#!/usr/bin/env python3
"""Controlled same-model A/B orchestration harness for Habitat.

Alpha.10 adds independent-evaluator support, diff fingerprints and paired summaries. The harness still
contains no model and never treats agent self-report as sufficient evidence when an evaluator is used.
"""
from __future__ import annotations

import argparse, hashlib, json, os, random, shlex, shutil, subprocess, sys, tempfile, time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.heldout_fixtures import materialize_fixture
from habitat.benchmarking import (
    BENCHMARK_CLASSES,
    AblationConfig,
    BenchmarkMetrics,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkSpec,
    EvaluationResult,
    ExperimentPlan,
    RecordedBenchmarkResult,
    admit_experiment_results,
    compare_conditions,
)

REQUIRED_RESULT={"success":bool,"task_id":str,"tool_calls":int,"input_tokens":int,"output_tokens":int,"wall_ms":int}
_OPTIONAL_METRICS=("exact_source_bytes","context_precision_proxy","context_recall_proxy","irrelevant_object_admission","ingest_ms","warm_reconcile_ms","provider_calls","failed_strategy_count","repeated_strategy_count","verification_count","mutation_rollback_count","mutation_conflict_count")
_METRIC_FIELDS=("input_tokens","output_tokens","tool_calls","exact_source_bytes","context_precision_proxy","context_recall_proxy","irrelevant_object_admission","wall_ms","ingest_ms","warm_reconcile_ms","provider_calls","failed_strategy_count","repeated_strategy_count","verification_count","mutation_rollback_count","mutation_conflict_count")


def load_suite(path: Path):
    value=json.loads(path.read_text(encoding="utf-8")); tasks=value.get("tasks") if isinstance(value,dict) else None
    if not isinstance(tasks,list) or not tasks: raise ValueError("suite requires non-empty tasks array")
    for t in tasks:
        if not isinstance(t,dict) or not isinstance(t.get("id"),str) or not isinstance(t.get("repo"),str) or not isinstance(t.get("prompt"),str):
            raise ValueError("each task requires id/repo/prompt strings")
    return value


def load_strong_suite(path: Path) -> dict:
    value=json.loads(path.read_text(encoding="utf-8")); tasks=value.get("tasks") if isinstance(value,dict) else None
    if not isinstance(value,dict) or not isinstance(value.get("suite_id"),str) or not value["suite_id"].strip():
        raise ValueError("strong suite requires non-empty suite_id")
    if not isinstance(tasks,list) or not tasks:
        raise ValueError("strong suite requires non-empty tasks array")
    seen=set()
    for task in tasks:
        if not isinstance(task,dict):
            raise ValueError("strong suite tasks must be objects")
        for key in ("id","benchmark_class","fixture_id","prompt"):
            if not isinstance(task.get(key),str) or not task[key].strip():
                raise ValueError(f"strong suite task requires non-empty {key}")
        if task["benchmark_class"] not in BENCHMARK_CLASSES:
            raise ValueError(f"unknown benchmark class: {task['benchmark_class']}")
        if task["id"] in seen:
            raise ValueError(f"duplicate task id: {task['id']}")
        seen.add(task["id"])
        budget=task.get("budget") or {}
        if not isinstance(budget,dict):
            raise ValueError("strong suite task budget must be an object")
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


def _serialize_ablation(ablation: AblationConfig) -> dict:
    return {
        "disabled_subsystems": sorted(ablation.disabled_subsystems),
        "semantic_mode": ablation.semantic_mode,
        "retrieval_policy": ablation.retrieval_policy,
    }


def _parse_ablation(raw: str) -> AblationConfig:
    try:
        value=json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Habitat ablation JSON: {exc}") from exc
    if not isinstance(value,dict):
        raise ValueError("Habitat ablation must be a JSON object")
    unknown=set(value)-{"disabled_subsystems","semantic_mode","retrieval_policy"}
    if unknown:
        raise ValueError(f"unknown Habitat ablation field: {sorted(unknown)[0]}")
    disabled=value.get("disabled_subsystems",[])
    if not isinstance(disabled,list) or not all(isinstance(item,str) for item in disabled):
        raise ValueError("disabled_subsystems must be a JSON string array")
    return AblationConfig(
        disabled_subsystems=frozenset(disabled),
        semantic_mode=value.get("semantic_mode","default"),
        retrieval_policy=value.get("retrieval_policy","default"),
    )


def _strong_task_fingerprint(task: dict, materialized_fingerprint: str) -> str:
    payload={
        "task_id":task["id"],
        "benchmark_class":task["benchmark_class"],
        "fixture_id":task["fixture_id"],
        "prompt":task["prompt"],
        "budget":task.get("budget") or {},
        "fixture_task_fingerprint":materialized_fingerprint,
    }
    raw=json.dumps(payload,sort_keys=True,ensure_ascii=True,separators=(",",":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _receipt_fields(planned) -> dict:
    return {
        "planned_run_identity":planned.identity,
        "environment_fingerprint":planned.environment_fingerprint,
        "condition_id":planned.condition_id,
        "repetition":planned.repetition,
        "seed":planned.seed,
        "ablation_fingerprint":planned.ablation.fingerprint,
        "model_id":planned.model_id,
        "scaffold_id":planned.scaffold_id,
        "evaluator_id":planned.evaluator_id,
    }


def _receipt_valid(result: dict, planned) -> bool:
    receipt=result.get("execution_receipt")
    if not isinstance(receipt,dict) or receipt != _receipt_fields(planned):
        return False
    return result.get("model_id")==planned.model_id and result.get("scaffold_id")==planned.scaffold_id


def run_strong_agent(command: str, task: dict, repo: Path, planned, timeout_s: int) -> dict:
    ablation=_serialize_ablation(planned.ablation)
    control={**_receipt_fields(planned),"ablation":ablation,"spec_fingerprint":planned.spec_fingerprint,"experiment_id":planned.experiment_id}
    env=os.environ.copy(); env.update({
        "HABITAT_AB_STRONG_EVIDENCE":"1",
        "HABITAT_AB_ARM":planned.arm,
        "HABITAT_AB_REPO":str(repo),
        "HABITAT_AB_TASK_ID":task["id"],
        "HABITAT_AB_CONDITION_ID":planned.condition_id,
        "HABITAT_AB_REPETITION":str(planned.repetition),
        "HABITAT_AB_SEED":str(planned.seed),
        "HABITAT_AB_PLANNED_RUN_ID":planned.identity,
        "HABITAT_AB_ENVIRONMENT_FINGERPRINT":planned.environment_fingerprint,
        "HABITAT_AB_ABLATION":json.dumps(ablation,sort_keys=True,separators=(",",":")),
        "HABITAT_AB_ABLATION_FINGERPRINT":planned.ablation.fingerprint,
        "HABITAT_AB_MODEL_ID":planned.model_id,
        "HABITAT_AB_SCAFFOLD_ID":planned.scaffold_id,
        "HABITAT_AB_EVALUATOR_ID":planned.evaluator_id,
    })
    payload={"task_id":task["id"],"prompt":task["prompt"],"repo":str(repo),"arm":planned.arm,"budget":task.get("budget") or {},"benchmark_control":control}
    started=time.monotonic()
    p=subprocess.run(command_args(command),input=json.dumps(payload),text=True,capture_output=True,timeout=timeout_s,env=env,cwd=repo,shell=False)
    elapsed=int((time.monotonic()-started)*1000)
    if p.returncode!=0:
        return {"task_id":task["id"],"success":False,"agent_claimed_success":False,"harness_error":"agent-command-failed","returncode":p.returncode,"stderr":p.stderr[-4000:],"observed_wall_ms":elapsed,"arm":planned.arm,"condition_id":planned.condition_id,"repetition":planned.repetition,"seed":planned.seed,"planned_run_identity":planned.identity,"receipt_valid":False,**git_diff_fingerprint(repo)}
    try:
        result=json.loads(p.stdout)
    except Exception as exc:
        return {"task_id":task["id"],"success":False,"agent_claimed_success":False,"harness_error":f"invalid-json-result:{exc}","stdout":p.stdout[-4000:],"observed_wall_ms":elapsed,"arm":planned.arm,"condition_id":planned.condition_id,"repetition":planned.repetition,"seed":planned.seed,"planned_run_identity":planned.identity,"receipt_valid":False,**git_diff_fingerprint(repo)}
    if not isinstance(result,dict):
        raise ValueError("strong agent result must be a JSON object")
    for key,typ in REQUIRED_RESULT.items():
        if key not in result or not isinstance(result[key],typ) or (isinstance(result[key],bool) and typ is int):
            raise ValueError(f"agent result missing/invalid {key}")
    result["agent_claimed_success"]=bool(result["success"])
    result["observed_wall_ms"]=elapsed
    result["arm"]=planned.arm
    result["condition_id"]=planned.condition_id
    result["repetition"]=planned.repetition
    result["seed"]=planned.seed
    result["planned_run_identity"]=planned.identity
    result["ablation"]=_serialize_ablation(planned.ablation)
    result["ablation_fingerprint"]=planned.ablation.fingerprint
    result["receipt_valid"]=_receipt_valid(result,planned)
    result.update(git_diff_fingerprint(repo))
    return result


def run_strong_evaluator(command: str, task: dict, repo: Path, agent_result: dict, evaluator_payload: dict, timeout_s: int) -> dict:
    payload={"workspace":str(repo),"task_id":task["id"],"prompt":task["prompt"],"agent_result":agent_result,"evaluator_payload":evaluator_payload}
    p=subprocess.run(command_args(command),input=json.dumps(payload),text=True,capture_output=True,timeout=timeout_s,cwd=repo,shell=False)
    if p.returncode!=0:
        return {"ok":False,"success":False,"error":"evaluator-command-failed","returncode":p.returncode,"stderr":p.stderr[-4000:]}
    try:
        value=json.loads(p.stdout)
    except Exception as exc:
        return {"ok":False,"success":False,"error":f"invalid-evaluator-json:{exc}","stdout":p.stdout[-4000:]}
    if not isinstance(value,dict) or not isinstance(value.get("success"),bool):
        raise ValueError("evaluator result requires boolean success")
    for key in ("regression_free","hidden_test_success"):
        if value.get(key) is not None and not isinstance(value.get(key),bool):
            raise ValueError(f"evaluator result {key} must be boolean or null")
    return {"ok":True,**value}


def _strong_metrics(result: dict) -> BenchmarkMetrics:
    values={name:result.get(name) for name in _OPTIONAL_METRICS}
    return BenchmarkMetrics(
        input_tokens=result.get("input_tokens"),
        output_tokens=result.get("output_tokens"),
        tool_calls=result.get("tool_calls"),
        wall_ms=result.get("observed_wall_ms"),
        **values,
    )


def _serialize_metrics(metrics: BenchmarkMetrics) -> dict:
    return {field_name:getattr(metrics,field_name) for field_name in _METRIC_FIELDS}


def _serialize_comparison(comparison) -> dict:
    return {
        "baseline_condition_id":comparison.baseline_condition_id,
        "candidate_condition_id":comparison.candidate_condition_id,
        "repetitions_compared":comparison.repetitions_compared,
        "pairs":[
            {
                "repetition":pair.repetition,
                "seed":pair.seed,
                "baseline_run_identity":pair.baseline_run_identity,
                "candidate_run_identity":pair.candidate_run_identity,
                "baseline_success":pair.baseline_success,
                "candidate_success":pair.candidate_success,
                "success_delta":pair.success_delta,
                "metric_deltas":{
                    metric_name:{"baseline":delta.baseline,"candidate":delta.candidate,"delta":delta.delta}
                    for metric_name,delta in pair.metric_deltas
                },
            }
            for pair in comparison.pairs
        ],
    }


def _serialize_plan(plan: ExperimentPlan) -> dict:
    return {
        "experiment_id":plan.experiment_id,
        "spec_fingerprint":plan.spec.fingerprint,
        "model_id":plan.model_id,
        "scaffold_id":plan.scaffold_id,
        "evaluator_id":plan.evaluator_id,
        "environment_fingerprint":plan.environment_fingerprint,
        "seeds":list(plan.seeds),
        "conditions":[
            {"condition_id":condition_id,"arm":arm,"ablation":_serialize_ablation(ablation),"ablation_fingerprint":ablation.fingerprint}
            for condition_id,arm,ablation in plan.conditions
        ],
        "planned_run_identities":[run.identity for run in plan.planned_runs()],
    }


def run_strong_experiments(args, ablations: tuple[AblationConfig,...]) -> dict:
    suite=load_strong_suite(Path(args.suite)); runs=[]; experiments=[]
    seeds=tuple(args.seed+rep for rep in range(args.repetitions))
    with tempfile.TemporaryDirectory(prefix="habitat-ab-strong-") as td:
        base=Path(td)
        for task_index,task in enumerate(suite["tasks"]):
            source=base/f"source-{task_index:04d}"
            nonce=hashlib.sha256(f"{suite['suite_id']}\0{task['id']}\0{args.seed}".encode("utf-8")).hexdigest()
            fixture=materialize_fixture(task["fixture_id"],source,nonce)
            spec=BenchmarkSpec(
                task_id=task["id"],
                benchmark_class=task["benchmark_class"],
                repository_revision=fixture.repository_revision,
                task_fingerprint=_strong_task_fingerprint(task,fixture.task_fingerprint),
            )
            experiment_id=hashlib.sha256(f"{suite['suite_id']}\0{spec.fingerprint}".encode("utf-8")).hexdigest()
            plan=ExperimentPlan(
                experiment_id=experiment_id,
                spec=spec,
                model_id=args.model_id,
                scaffold_id=args.scaffold_id,
                evaluator_id=args.evaluator_id,
                environment_fingerprint=args.environment_fingerprint,
                seeds=seeds,
                habitat_ablations=ablations,
            )
            records=[]; attempted_records=[]
            for order_index,planned in enumerate(plan.planned_runs()):
                repo=base/f"run-{task_index:04d}-{order_index:04d}-{planned.identity[:12]}"
                clone_repo(source,repo)
                command=args.baseline_cmd if planned.arm=="filesystem" else args.habitat_cmd
                result=run_strong_agent(command,task,repo,planned,args.timeout)
                evaluation=run_strong_evaluator(args.evaluator_cmd,task,repo,result,fixture.evaluator_payload,args.timeout)
                result["evaluation"]=evaluation
                result["success"]=bool(evaluation.get("success"))
                runs.append(result)

                metrics=None; metrics_error=None
                try:
                    metrics=_strong_metrics(result)
                except (TypeError,ValueError) as exc:
                    metrics_error=str(exc)

                admitted=False; rejection_reason=None
                if not result.get("receipt_valid"):
                    rejection_reason="execution-receipt-mismatch"
                elif not evaluation.get("ok"):
                    rejection_reason="evaluator-not-admissible"
                elif metrics is None:
                    rejection_reason="invalid-benchmark-metrics"
                else:
                    run=BenchmarkRun(
                        spec_fingerprint=spec.fingerprint,
                        arm=planned.arm,
                        repetition=planned.repetition,
                        seed=planned.seed,
                        model_id=planned.model_id,
                        scaffold_id=planned.scaffold_id,
                        metrics=metrics,
                        ablation=planned.ablation,
                        agent_claimed_success=result.get("agent_claimed_success"),
                    )
                    evaluated=EvaluationResult(
                        evaluator_id=planned.evaluator_id,
                        success=bool(evaluation["success"]),
                        regression_free=evaluation.get("regression_free"),
                        hidden_test_success=evaluation.get("hidden_test_success"),
                    )
                    records.append(RecordedBenchmarkResult(
                        planned_run_identity=planned.identity,
                        environment_fingerprint=planned.environment_fingerprint,
                        result=BenchmarkResult(spec=spec,run=run,evaluation=evaluated),
                    ))
                    admitted=True

                attempted_records.append({
                    "planned_run_identity":planned.identity,
                    "condition_id":planned.condition_id,
                    "arm":planned.arm,
                    "repetition":planned.repetition,
                    "seed":planned.seed,
                    "ablation":_serialize_ablation(planned.ablation),
                    "ablation_fingerprint":planned.ablation.fingerprint,
                    "receipt_valid":bool(result.get("receipt_valid")),
                    "admitted":admitted,
                    "rejection_reason":rejection_reason,
                    "metrics":_serialize_metrics(metrics) if metrics is not None else None,
                    "metrics_error":metrics_error,
                    "evaluation":evaluation,
                })

            evidence=admit_experiment_results(plan,records)
            comparisons=[_serialize_comparison(compare_conditions(evidence,"filesystem","habitat"))]
            comparisons.extend(
                _serialize_comparison(compare_conditions(evidence,"habitat",f"habitat:{ablation.fingerprint}"))
                for ablation in ablations
            )
            experiments.append({
                "task_id":task["id"],
                "benchmark_class":task["benchmark_class"],
                "repository_revision":spec.repository_revision,
                "task_fingerprint":spec.task_fingerprint,
                "plan":_serialize_plan(plan),
                "complete":evidence.complete,
                "missing_run_identities":list(evidence.missing_run_identities),
                "admitted_run_identities":[record.planned_run_identity for record in evidence.records],
                "records":attempted_records,
                "comparisons":comparisons,
            })
    base_runs=[run for run in runs if run.get("condition_id") in {"filesystem","habitat"}]
    return {"suite":suite,"runs":runs,"experiments":experiments,"paired_summary":paired_summary(base_runs)}


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
    ap.add_argument("--habitat-ablation",action="append",default=[])
    args=ap.parse_args()
    if args.repetitions<1 or args.repetitions>50: raise ValueError("repetitions must be in [1,50]")
    if args.strong_evidence:
        if args.repetitions<3: ap.error("strong evidence requires at least 3 repetitions")
        for option,value in (("--model-id",args.model_id),("--scaffold-id",args.scaffold_id),("--evaluator-id",args.evaluator_id),("--environment-fingerprint",args.environment_fingerprint),("--evaluator-cmd",args.evaluator_cmd)):
            if not isinstance(value,str) or not value.strip(): ap.error(f"{option} is required in strong evidence mode")
        if args.seed<0: ap.error("--seed must be non-negative in strong evidence mode")
        try:
            ablations=tuple(_parse_ablation(raw) for raw in args.habitat_ablation)
            strong=run_strong_experiments(args,ablations)
        except (TypeError,ValueError,KeyError,FileNotFoundError) as exc:
            ap.error(str(exc))
        runs=strong["runs"]
        comparability={
            "same_model_observed":all(run.get("model_id")==args.model_id for run in runs),
            "same_scaffold_observed":all(run.get("scaffold_id")==args.scaffold_id for run in runs),
            "independent_evaluator":True,
            "all_execution_receipts_valid":all(bool(run.get("receipt_valid")) for run in runs),
            "strong_evidence_ready":all(exp["complete"] for exp in strong["experiments"]),
            "reasons":[],
        }
        if not comparability["all_execution_receipts_valid"]:
            comparability["reasons"].append("one or more execution receipts were missing or inconsistent")
        if not comparability["strong_evidence_ready"]:
            comparability["reasons"].append("one or more planned runs were not admitted")
        report={
            "schema":3,
            "strong_evidence_mode":True,
            "same_model_required":True,
            "same_scaffold_required":True,
            "seed":args.seed,
            "repetitions":args.repetitions,
            "tasks":len(strong["suite"]["tasks"]),
            "runs":runs,
            "evaluator_required_for_strong_evidence":True,
            "independent_evaluator_used":True,
            "observed_model_ids":[args.model_id],
            "observed_scaffold_ids":[args.scaffold_id],
            "comparability":comparability,
            "paired_summary":strong["paired_summary"],
            "benchmark_lab":{"schema":1,"experiments":strong["experiments"]},
            "claim_boundary":"Strong mode binds one mutation-derived source revision to an explicit typed experiment plan, uses the same Habitat command for base and ablation conditions, requires matching execution receipts, and uses an independent evaluator. Receipts attest scaffold-applied configuration but are not cryptographic proof of internal model behavior.",
        }
        Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True),encoding="utf-8")
        print(json.dumps({"out":args.out,"runs":len(runs),"pairs":report["paired_summary"]["pair_count"]},sort_keys=True))
        return
    if args.habitat_ablation:
        ap.error("--habitat-ablation requires --strong-evidence")
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
