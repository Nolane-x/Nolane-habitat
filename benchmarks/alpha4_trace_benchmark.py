from __future__ import annotations
import argparse, json, re, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.protocol import HabitatProtocol
from habitat.workspace import HabitatWorkspace

STOP={'the','a','an','and','or','to','in','of','for','is','are','it','this','that','where','what','how','with','fix','find','implement','behavior'}
def terms(task): return [x.lower() for x in re.findall(r'[A-Za-z_][A-Za-z0-9_]{2,}',task) if x.lower() not in STOP]

def build(root:Path,noise=120):
    root.mkdir(parents=True,exist_ok=True)
    (root/'auth.py').write_text('def validate_credentials(email,password):\n    """credential validation login"""\n    return bool(email) and password == "secret"\n')
    (root/'billing.py').write_text('def calculate_invoice_tax(amount,rate):\n    """invoice tax billing"""\n    return amount*rate\n')
    for i in range(noise): (root/f'noise_{i:03d}.py').write_text(f'def helper_{i}(value):\n    return value\n')

def fs_scan(root:Path,task:str):
    wanted=terms(task); files=0; b=0; hits=[]
    for p in sorted(root.glob('*.py')):
        data=p.read_bytes(); files+=1; b+=len(data); txt=data.decode(errors='replace').lower(); score=sum(txt.count(x) for x in wanted)
        if score: hits.append((score,p.name))
    hits.sort(key=lambda x:(-x[0],x[1])); return {'files_read':files,'source_bytes_read':b,'navigation_operations':files+1,'top_paths':[x[1] for x in hits[:8]],'definition':'deterministic full-text scan, not an agent'}

def traced_case(proto:HabitatProtocol,task:str,label:str):
    tid=proto.handle({'id':'s','method':'workspace.trace.start','params':{'label':label}})['result']['trace_id']
    ctx=proto.handle({'id':'o','method':'workspace.orient','params':{'task':task,'budget':8}})['result']
    packet=proto.handle({'id':'m','method':'workspace.context.materialize','params':{'handle':ctx['handle'],'max_source_bytes':6000,'max_objects':8}})['result']
    trace=proto.handle({'id':'e','method':'workspace.trace.stop','params':{'trace_id':tid}})['result']
    return {'context':{'handle':ctx['handle'],'paths':[x['path'] for x in ctx['objects']],'lanes':[x['lane'] for x in ctx['objects']]},'packet':{'object_count':packet['object_count'],'exact_source_bytes':packet['source_bytes'],'packet_bytes':packet['packet_bytes']},'trace':trace}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output'); ap.add_argument('--noise-files',type=int,default=120); args=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); project=base/'project'; build(project,args.noise_files); ws=HabitatWorkspace.create(project,base/'habitat'); proto=HabitatProtocol(ws)
        cold=traced_case(proto,'fix credential validation login','cold-related-task')
        ws.residency_configure(6,20000); ws.residency_admit(cold['context']['handle'],pin_top=1)
        warm=traced_case(proto,'review credential validation logic','resident-related-task')
        unrelated=traced_case(proto,'find invoice tax billing','unrelated-task')
        report={'release':'0.1.0-alpha.4','benchmark':'protocol-trace-plumbing-v1','fixture':{'files':ws.enter()['file_count'],'noise_files':args.noise_files},
                'filesystem':{'credential':fs_scan(project,'fix credential validation login'),'billing':fs_scan(project,'find invoice tax billing')},
                'habitat':{'cold_related':cold,'resident_related':warm,'unrelated':unrelated},
                'instrumentation_guarantee':'Counts protocol calls and serialized bytes observed by Habitat; exact_source_bytes counts only responses marked as exact-source authority.',
                'claim_boundary':'Not an LLM A/B. No token, reasoning, success-rate, or universal speed claim is admitted from this harness.'}
        ws.close()
    text=json.dumps(report,indent=2,ensure_ascii=False)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()
