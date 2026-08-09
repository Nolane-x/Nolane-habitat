from __future__ import annotations
import argparse,json,re,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace
from habitat.protocol import HabitatProtocol

STOP={'the','a','an','and','or','to','in','of','for','is','are','it','this','that','where','what','how','with','fix','find','implement','behavior'}
def terms(task): return [x.lower() for x in re.findall(r'[A-Za-z_][A-Za-z0-9_]{2,}',task) if x.lower() not in STOP]
def build(root:Path,noise:int):
    root.mkdir(parents=True,exist_ok=True)
    (root/'auth.py').write_text('def validate_credentials(email,password):\n    """credential validation login"""\n    return bool(email) and password == "secret"\n')
    (root/'billing.py').write_text('def calculate_invoice_tax(amount,rate):\n    """invoice tax billing"""\n    return amount*rate\n')
    for i in range(noise): (root/f'noise_{i:03d}.py').write_text(f'def helper_{i}(value):\n    return value\n')
def fs_scan(root:Path,task:str):
    wanted=terms(task); files=b=0; hits=[]
    for p in sorted(root.glob('*.py')):
        raw=p.read_bytes(); files+=1; b+=len(raw); text=raw.decode(errors='replace').lower(); score=sum(text.count(x) for x in wanted)
        if score: hits.append((score,p.name))
    hits.sort(key=lambda x:(-x[0],x[1])); return {'files_read':files,'source_bytes_read':b,'top_paths':[x[1] for x in hits[:8]]}
def habitat_case(proto,task,label):
    proto.handle({'id':'s','method':'workspace.trace.start','params':{'label':label}})
    ctx=proto.handle({'id':'o','method':'workspace.orient','params':{'task':task,'budget':8}})['result']
    plan=proto.handle({'id':'n','method':'workspace.context.plan_next','params':{'handle':ctx['handle'],'max_pages':6,'max_estimated_bytes':5000}})['result']
    if plan.get('page_ids'):
        packet=proto.handle({'id':'p','method':'workspace.context.fetch','params':{'handle':ctx['handle'],'page_ids':plan['page_ids'],'max_source_bytes':5000}})['result']
    else:
        packet={'source_bytes':0,'pages':[],'faults':[]}
    trace=proto.handle({'id':'e','method':'workspace.trace.stop','params':{}})['result']
    return {'paths':[x['path'] for x in ctx['objects']],'confidence':ctx['decision_packet']['retrieval_confidence'],
            'abstain':ctx['decision_packet']['abstention_recommended'],'plan_action':plan.get('action'),'source_bytes':packet['source_bytes'],
            'page_count':len(packet.get('pages',[])),'trace':trace}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--noise-files',type=int,default=200); ap.add_argument('--output'); args=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/'project'; build(root,args.noise_files); ws=HabitatWorkspace.create(root,Path(td)/'habitat'); proto=HabitatProtocol(ws)
        cases={
          'credential':('fix credential validation login','auth.py'),
          'billing':('find invoice tax billing','billing.py'),
          'no_gold':('quantum banana teleportation matrix',None),
        }
        habitat={}; filesystem={}
        for name,(task,gold) in cases.items():
            filesystem[name]=fs_scan(root,task); habitat[name]=habitat_case(proto,task,name); habitat[name]['gold_path']=gold
            habitat[name]['gold_retrieved']=gold in habitat[name]['paths'] if gold else None
            habitat[name]['noise_paths']=[p for p in habitat[name]['paths'] if p.startswith('noise_')]
        report={'release':'0.1.0-alpha.6','benchmark':'context-precision-plumbing-v3','fixture':{'files':ws.enter()['file_count'],'noise_files':args.noise_files},
                'filesystem_full_scan':filesystem,'habitat':habitat,
                'metrics_definition':'Deterministic retrieval/source-byte instrumentation with gold paths and a no-gold abstention case.',
                'claim_boundary':'Not a same-model agent A/B. It supports only retrieval/planner plumbing claims, not token, reasoning, speed, or coding-success claims.'}
        ws.close()
    text=json.dumps(report,indent=2,ensure_ascii=False,default=str)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()
