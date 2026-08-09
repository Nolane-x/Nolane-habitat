from __future__ import annotations
import argparse,json,re,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace

RELEASE='0.1.0-alpha.8'
STOP={'the','a','an','and','or','to','in','of','for','is','are','it','this','that','where','what','how','with','fix','find','implement','behavior'}
def terms(task): return [x.lower() for x in re.findall(r'[A-Za-z_][A-Za-z0-9_]{2,}',task) if x.lower() not in STOP]
def build(root:Path,noise:int):
    root.mkdir(parents=True,exist_ok=True)
    (root/'auth.py').write_text('def validate_credentials(email,password):\n    """credential validation login"""\n    return bool(email) and password == "secret"\n')
    (root/'billing.py').write_text('def calculate_invoice_tax(amount,rate):\n    """invoice tax billing"""\n    return amount*rate\n')
    for i in range(noise): (root/f'noise_{i:03d}.py').write_text(f'def helper_{i}(value):\n    return value\n')
def full_scan(root,task):
    wanted=terms(task); files=bytes_=lines=0; hits=[]
    for p in sorted(root.glob('*.py')):
        raw=p.read_bytes(); files+=1; bytes_+=len(raw); text=raw.decode(errors='replace'); lines+=max(1,len(text.splitlines())); score=sum(text.lower().count(x) for x in wanted)
        if score: hits.append((score,p.name))
    hits.sort(key=lambda x:(-x[0],x[1])); return {'files_read':files,'source_bytes_read':bytes_,'source_lines_read':lines,'top_paths':[x[1] for x in hits[:8]]}
def hcase(ws,task,gold,line_budget=12):
    exp=ws.explore(task,line_budget=line_budget,max_regions=5,context_budget=12)
    if exp['abstained']:
        fetched={'source_bytes':0,'pages':[]}
    else:
        plan=ws.context_plan_next(exp['context_handle'],max_pages=2,max_estimated_bytes=4000)
        fetched=ws.context_fetch_pages(exp['context_handle'],plan.get('page_ids',[]),4000)
    paths=[r['path'] for r in exp['regions']]
    return {'confidence':exp['retrieval_confidence'],'abstained':exp['abstained'],'regions':exp['regions'],'lines_selected':exp['lines_selected'],
            'explorer_source_bytes':exp['source_bytes_read'],'solver_faulted_source_bytes':fetched['source_bytes'],'gold_path':gold,
            'gold_region_retrieved':gold in paths if gold else None,'noise_regions':[p for p in paths if p.startswith('noise_')]}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--noise-files',type=int,default=200); ap.add_argument('--output'); args=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/'project'; build(root,args.noise_files)
        with HabitatWorkspace.create(root,Path(td)/'habitat') as ws:
            cases={'credential':('fix credential validation login','auth.py'),'billing':('find invoice tax billing','billing.py'),'no_gold':('quantum banana teleportation matrix',None)}
            fs={}; habitat={}
            for name,(task,gold) in cases.items(): fs[name]=full_scan(root,task); habitat[name]=hcase(ws,task,gold)
            report={'release':RELEASE,'benchmark':'line-budget-explorer-plumbing-v1','fixture':{'files':ws.enter()['file_count'],'noise_files':args.noise_files},
                    'filesystem_full_scan':fs,'habitat':habitat,
                    'metrics_definition':'Deterministic semantic region selection under line budget plus exact-source page-fault bytes; explorer reads zero source bytes.',
                    'claim_boundary':'Not a same-model agent A/B. Source bytes and line budgets are not token counts and do not establish coding success.'}
    text=json.dumps(report,indent=2,ensure_ascii=False,default=str)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()
