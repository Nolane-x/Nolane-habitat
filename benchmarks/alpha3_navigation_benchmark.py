from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace

STOP={"the","a","an","and","or","to","in","of","for","is","are","it","this","that","where","what","how","with","fix","find","implement","behavior"}


def terms(task: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}",task) if x.lower() not in STOP]


def build_fixture(root: Path, noise_files: int = 120) -> dict[str,str]:
    root.mkdir(parents=True,exist_ok=True)
    targets={
        "credential": ("auth.py","validate_credentials","credential validation for login"),
        "billing": ("billing.py","calculate_invoice_tax","invoice tax calculation billing"),
        "avatar": ("profile.py","normalize_avatar_url","profile avatar url normalization"),
    }
    (root/'auth.py').write_text('def validate_credentials(email, password):\n    """credential validation for login"""\n    return bool(email) and password == "secret"\n')
    (root/'billing.py').write_text('def calculate_invoice_tax(amount, rate):\n    """invoice tax calculation billing"""\n    return amount * rate\n')
    (root/'profile.py').write_text('def normalize_avatar_url(value):\n    """profile avatar url normalization"""\n    return value.strip()\n')
    (root/'service.py').write_text('import auth\nimport billing\nimport profile\n\ndef login(e,p): return auth.validate_credentials(e,p)\n')
    for i in range(noise_files):
        body=(f'"""noise subsystem {i} generic project support utilities"""\n'
              f'def helper_{i}(value):\n    return value\n')
        (root/f'noise_{i:03d}.py').write_text(body)
    return {k:f"{v[0]}::{v[1]}" for k,v in targets.items()}


def fs_baseline(root: Path, task: str, target_path: str, target_symbol: str) -> dict:
    wanted=terms(task)
    t=time.perf_counter(); bytes_read=0; files_read=0; scored=[]
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.suffix.lower() not in {'.py','.js','.ts','.tsx','.java','.html','.md'}:
            continue
        data=p.read_bytes(); bytes_read += len(data); files_read += 1
        text=data.decode('utf-8',errors='replace').lower()
        score=sum(text.count(x) for x in wanted)
        if score:
            scored.append((score,p.relative_to(root).as_posix()))
    scored.sort(key=lambda x:(-x[0],x[1]))
    top=[p for _,p in scored[:8]]
    found=target_path in top
    return {
        'target_found':found,'top_paths':top,'files_read':files_read,'source_bytes_read':bytes_read,
        'navigation_operations':files_read + 1,
        'elapsed_ms':round((time.perf_counter()-t)*1000,3),
        'baseline_definition':'deterministic full-text filesystem scan; not an LLM agent',
        'target_symbol':target_symbol,
    }


def habitat_path(ws: HabitatWorkspace, task: str, target_path: str, target_symbol: str) -> dict:
    t=time.perf_counter(); ctx=ws.orient(task,budget=10); orient_ms=(time.perf_counter()-t)*1000
    selected=[o for o in ctx.objects]
    target_obj=None
    for o in selected:
        if o.path != target_path:
            continue
        row=ws.store.symbol_by_id(o.object_id)
        if row is not None and row['name'] == target_symbol:
            target_obj=o; break
    inspect_bytes=0; inspected=[]
    # Simulate a decision engine asking exact source only for the first few semantic objects.
    for o in selected[:5]:
        if ws.store.symbol_by_id(o.object_id):
            val=ws.inspect(o.object_id,'body'); src=val.get('source',''); inspect_bytes += len(src.encode('utf-8')); inspected.append(o.object_id)
            if o.object_id == (target_obj.object_id if target_obj else None):
                break
    context_wire=len(json.dumps({'objects':[o.__dict__ for o in selected],'unknowns':ctx.unknowns},ensure_ascii=False).encode('utf-8'))
    return {
        'target_found':target_obj is not None,
        'target_object_id':target_obj.object_id if target_obj else None,
        'selected_paths':[o.path for o in selected],
        'exact_source_bytes_requested':inspect_bytes,
        'context_packet_bytes':context_wire,
        'agent_api_calls':1+len(inspected),
        'orient_ms':round(orient_ms,3),
        'inspected_object_ids':inspected,
        'target_symbol':target_symbol,
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output'); ap.add_argument('--noise-files',type=int,default=120); args=ap.parse_args()
    tasks=[
        ('credential','fix credential validation in login behavior','auth.py','validate_credentials'),
        ('billing','find invoice tax calculation in billing','billing.py','calculate_invoice_tax'),
        ('avatar','fix profile avatar url normalization','profile.py','normalize_avatar_url'),
    ]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); project=root/'project'; build_fixture(project,args.noise_files)
        t=time.perf_counter(); ws=HabitatWorkspace.create(project,root/'habitat'); cold_ms=round((time.perf_counter()-t)*1000,3)
        enter=ws.enter(); cases=[]
        for cid,task,path,symbol in tasks:
            cases.append({'id':cid,'task':task,'filesystem':fs_baseline(project,task,path,symbol),'habitat':habitat_path(ws,task,path,symbol)})
        all_success=all(c['filesystem']['target_found'] and c['habitat']['target_found'] for c in cases)
        report={
            'release':'0.1.0-alpha.3',
            'benchmark':'navigation-plumbing-ab-v1',
            'fixture':{'noise_files':args.noise_files,'project_files':enter['file_count'],'source_bytes':enter['index_health']['source_bytes']},
            'habitat_cold_ingest_ms':cold_ms,
            'cases':cases,
            'all_targets_found_by_both':all_success,
            'interpretation':{
                'valid':'Compares deterministic per-task filesystem scanning with warm Habitat orientation on the same synthetic source tree.',
                'invalid':'Does not measure an LLM, token usage, coding-task success, reasoning quality, or universal speedup. Habitat cold ingest is disclosed separately and filesystem tooling could use better indexes than this baseline.',
            },
            'claim_boundary':'Plumbing benchmark only. A same-model external agent A/B harness is still required before any AI-efficiency claim.'
        }
        ws.close()
    text=json.dumps(report,indent=2)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)

if __name__=='__main__': main()
