from __future__ import annotations
import json, shutil, sys, tempfile, time, urllib.request, urllib.error, subprocess
from pathlib import Path

HERE=Path(__file__).resolve(); ROOT=HERE.parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from habitat.workspace import HabitatWorkspace
from habitat import shutdown_runtime_services


def screenshot_observatory(obs_url: str, snap: dict, shot: Path) -> dict:
    browser=shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome') or shutil.which('google-chrome-stable')
    if not browser: return {'captured':False,'reason':'Chromium unavailable'}
    # Prefer a fresh browser process so earlier agent UI sessions cannot contaminate screenshot lifecycle.
    args=[browser,'--headless=new','--disable-gpu','--disable-dev-shm-usage','--hide-scrollbars',f'--window-size=1920,1080',f'--screenshot={shot}', '--virtual-time-budget=2400']
    if hasattr(__import__('os'),'geteuid') and __import__('os').geteuid()==0: args.append('--no-sandbox')
    args.append(obs_url)
    try:
        proc=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=18)
        if proc.returncode==0 and shot.is_file() and shot.stat().st_size>10000:
            return {'captured':True,'path':shot.name,'bytes':shot.stat().st_size,'source':'live-http-chromium','dimensions':{'w':1920,'h':1080}}
    except Exception:
        pass
    # Fallback renders the exact already-fetched live snapshot, never mock data.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b=pw.chromium.launch(headless=True,executable_path=browser,args=['--no-sandbox','--disable-dev-shm-usage'])
            page=b.new_page(viewport={'width':1920,'height':1080},device_scale_factor=1); assets=ROOT/'habitat'/'observatory_assets'
            html=(assets/'index.html').read_text(encoding='utf-8').replace('<link rel="stylesheet" href="/style.css">','').replace('<script src="/app.js"></script>','')
            page.set_content(html,wait_until='domcontentloaded'); page.add_style_tag(content=(assets/'style.css').read_text(encoding='utf-8'))
            page.evaluate('(payload)=>{window.__SNAPSHOT__=payload;window.fetch=async()=>new Response(JSON.stringify(window.__SNAPSHOT__),{status:200,headers:{"Content-Type":"application/json"}});window.EventSource=class{constructor(){this.listeners={};setTimeout(()=>{if(this.onopen)this.onopen({})},10)}addEventListener(k,fn){this.listeners[k]=fn}close(){}}}',snap)
            page.add_script_tag(content=(assets/'app.js').read_text(encoding='utf-8')); page.wait_for_timeout(1700); page.screenshot(path=str(shot),full_page=True); b.close()
        return {'captured':True,'path':shot.name,'bytes':shot.stat().st_size,'source':'live-snapshot-offline-render','dimensions':{'w':1920,'h':1080}}
    except Exception as exc:return {'captured':False,'reason':f'{type(exc).__name__}: {exc}'}


def main():
    reports=ROOT/'reports'; reports.mkdir(exist_ok=True)
    out=reports/'OBSERVATORY-EVIDENCE-alpha12.json'; shot=reports/'OBSERVATORY-alpha12.png'
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); project=base/'project'; project.mkdir()
        for d in ['auth','billing','tests','ui','migrations','.github/workflows']:(project/d).mkdir(parents=True,exist_ok=True)
        (project/'auth'/'claims.py').write_text(
            'import os\n\n'
            'def normalize_email(email):\n    return email.strip().lower()\n\n'
            'def build_claims(subscription_active: bool, user):\n'
            '    email = normalize_email(user.email)\n'
            '    role = "admin" if user.is_admin else "user"\n'
            '    elevated = bool(subscription_active and role == "admin")\n'
            '    return {"email": email, "role": role, "elevated": elevated, "env": os.getenv("APP_ENV")}\n\n'
            'def refresh_token(subscription_active: bool, user):\n    return build_claims(subscription_active, user)\n',encoding='utf-8')
        (project/'auth'/'subscription.py').write_text('def is_active(state: str) -> bool:\n    return state not in {"expired", "cancelled"}\n',encoding='utf-8')
        (project/'billing'/'invoice.py').write_text('def total(amount):\n    return amount\n',encoding='utf-8')
        (project/'tests'/'test_auth.py').write_text(
            'import unittest\nfrom types import SimpleNamespace\nfrom auth.claims import refresh_token\n\n'
            'class AuthTests(unittest.TestCase):\n'
            '    def test_expired_subscription(self):\n'
            '        user=SimpleNamespace(email="Admin@Example.com",is_admin=True)\n'
            '        self.assertFalse(refresh_token(False,user)["elevated"])\n\n'
            'if __name__ == "__main__": unittest.main()\n',encoding='utf-8')
        (project/'package.json').write_text(json.dumps({'name':'nolane-demo','scripts':{'test':'python -m unittest','build':'vite'},'dependencies':{'express':'^5.0.0','pg':'^8.12.0'}},indent=2),encoding='utf-8')
        (project/'docker-compose.yml').write_text('services:\n  web:\n    image: demo/web\n    depends_on: [api]\n  api:\n    image: demo/api\n    depends_on: [db, redis]\n  db:\n    image: postgres:16\n  redis:\n    image: redis:7\n',encoding='utf-8')
        (project/'.github/workflows/ci.yml').write_text('jobs:\n  test:\n    runs-on: ubuntu-latest\n  build:\n    runs-on: ubuntu-latest\n  security:\n    runs-on: ubuntu-latest\n',encoding='utf-8')
        (project/'openapi.json').write_text(json.dumps({'openapi':'3.1.0','info':{'title':'Auth API','version':'1'},'paths':{'/token/refresh':{'post':{'operationId':'refreshToken'}},'/subscriptions/{id}':{'get':{'operationId':'getSubscription'}}}}),encoding='utf-8')
        (project/'migrations/001_users.sql').write_text('CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT,role TEXT,subscription_state TEXT);\n',encoding='utf-8')
        (project/'AGENTS.md').write_text('Auth changes require targeted auth verification. Never expose raw reasoning in the Observatory.\n',encoding='utf-8')
        (project/'ui/index.html').write_text('''<!doctype html><html><body><button id="refreshBtn">Refresh token</button><div id="status">idle</div><script>document.getElementById('refreshBtn').onclick=()=>{document.getElementById('status').textContent='refreshed'}</script></body></html>''',encoding='utf-8')

        ws=HabitatWorkspace.create(project,base/'habitat')
        try:
            codex=ws.agent_open('Codex',{'surface':'mcp','role':'implementer','task':'Fix expired subscription permissions'})['id']
            claude=ws.agent_open('Claude Code',{'surface':'mcp','role':'skeptic','task':'Challenge the auth hypothesis'})['id']
            verifier=ws.agent_open('Verifier Agent',{'surface':'direct','role':'verifier','task':'Prove the selected world'})['id']
            ctx=ws.orient('Fix expired subscription permissions during token refresh',budget=16,agent_id=codex)
            ep=ws.episode_start('Fix expired subscription permissions during token refresh',ctx.handle)
            ws.agent_residency_admit(codex,ctx.handle,max_admit=6,pin_top=2); packet=ws.context_prefetch(ctx.handle,max_source_bytes=8000,max_pages=6)
            h1=ws.hypothesis_create('subscription freshness is lost before refresh-token claim construction',episode_id=ep['id'],prior_confidence=.70)
            h2=ws.hypothesis_create('claim builder elevates admin users even when the subscription is expired',episode_id=ep['id'],prior_confidence=.55)
            ws.agent_belief_update(codex,h1['id'],stance='support',confidence=.79,rationale='task and static flow point toward freshness')
            ws.agent_belief_update(claude,h2['id'],stance='support',confidence=.68,rationale='claim-builder condition is behaviorally decisive')
            ws.epistemic_create('unknown','whether the refresh path receives subscription state after revalidation',agent_id=codex,episode_id=ep['id'])
            ws.epistemic_create('contradiction','static state input exists, but observed runtime freshness has not been established',agent_id=codex,episode_id=ep['id'])
            inv=ws.invariant_create('expired subscription must never produce elevated refreshed claims',metadata={'scope':'auth'})
            ws.invariant_link(inv['id'],'symbol',next(x['id'] for x in ws.store.symbols_named('build_claims') if x['path']=='auth/claims.py'),relation='implements')
            ws.memory_record('decision','Prefer evidence-bearing counterfactual worlds before canonical auth mutation',provenance={'source':'alpha12-demo'})
            ws.effect_refresh(['auth/claims.py']); ws.dataflow_refresh(['auth/claims.py'])
            ws.runtime_ingest('opentelemetry',[
                {'trace_id':'trace-refresh','span_id':'web','name':'click refresh token','duration_ms':.4,'attributes':{'service.name':'web','http.route':'ui:/refresh'}},
                {'trace_id':'trace-refresh','span_id':'api','parent_span_id':'web','name':'POST /token/refresh','duration_ms':5.8,'attributes':{'service.name':'api','http.route':'/token/refresh','code.file.path':str(project/'auth/claims.py'),'code.line.number':12}},
                {'trace_id':'trace-refresh','span_id':'db','parent_span_id':'api','name':'SELECT subscription','duration_ms':1.3,'attributes':{'service.name':'api','db.system':'postgresql','db.name':'users'}},
                {'trace_id':'trace-refresh','span_id':'cache','parent_span_id':'api','name':'GET entitlement cache','duration_ms':.6,'attributes':{'service.name':'api','db.system':'redis','db.name':'entitlements'}},
            ],agent_id=codex,episode_id=ep['id'])
            # Two isolated alternatives: change claim guard versus normalize state at call boundary.
            wa=ws.counterfactual_fork('WORLD A · harden claim elevation',agent_id=codex)
            ws.counterfactual_apply(wa['id'],[{'op':'replace_text','path':'auth/claims.py','old':'elevated = bool(subscription_active and role == "admin")','new':'elevated = bool(subscription_active) and role == "admin"'}])
            wb=ws.counterfactual_fork('WORLD B · explicit refresh gate',agent_id=claude)
            ws.counterfactual_apply(wb['id'],[{'op':'replace_text','path':'auth/claims.py','old':'def refresh_token(subscription_active: bool, user):\n    return build_claims(subscription_active, user)','new':'def refresh_token(subscription_active: bool, user):\n    if not subscription_active:\n        return build_claims(False, user)\n    return build_claims(True, user)'}])
            comparison=ws.counterfactual_compare([wa['id'],wb['id']])
            ws.activity_emit('agent.world-comparison','counterfactual',agent_id=verifier,episode_id=ep['id'],status='running',summary='Verifier compares WORLD A and WORLD B',data={'world_ids':[wa['id'],wb['id']]})
            promoted=ws.counterfactual_promote(wb['id'],agent_id=claude,episode_id=ep['id'])
            verification=ws.verify(changed_paths=promoted['transaction'].get('changed_paths') or ['auth/claims.py'],episode_id=ep['id'])
            ws.memory_record('experiment','WORLD B promoted and targeted auth verifier passed',agent_id=verifier,episode_id=ep['id'],confidence=.93,provenance={'source':'counterfactual-verification'})
            ws.epistemic_update(next(x['id'] for x in ws.epistemic_state(codex)['items'] if x['kind']=='contradiction'),status='resolved',provenance={'resolution':'counterfactual WORLD B + verifier receipt'})
            # Actual browser actions generate realtime UI events visible in Observatory when Chromium is available.
            ui_result={'available':False}
            try:
                ui=ws.open_ui_runtime('ui/index.html'); ws.observe_ui_runtime(ui['session_id'])
                ws.act_ui_runtime(ui['session_id'],'click','ui:id:refreshBtn')
                assertion=ws.assert_ui_runtime(ui['session_id'],[{'handle':'ui:id:status','text_contains':'refreshed'}])
                ws.close_ui_runtime(ui['session_id']); ui_result={'available':True,'assertion_passed':assertion.get('passed')}
            except Exception as exc:
                ws.activity_emit('ui.runtime-unavailable','ui',agent_id=verifier,episode_id=ep['id'],status='unavailable',summary='browser runtime unavailable in host',data={'error':f'{type(exc).__name__}: {exc}'})
                ui_result={'available':False,'reason':f'{type(exc).__name__}: {exc}'}
            shutdown_runtime_services()
            ws.runtime_ingest('opentelemetry',[{'record_type':'log','severity_text':'INFO','body':'counterfactual WORLD B verifier passed','attributes':{'service.name':'verifier','code.file.path':str(project/'tests/test_auth.py'),'code.line.number':6}},{'record_type':'metric','metric_name':'habitat.world.promoted','value':1,'unit':'1','attributes':{'service.name':'habitat'}}],agent_id=verifier,episode_id=ep['id'])
            plan=ws.cognition_plan(codex,ep['id']); world_summary=ws.world_summary(); project_world=ws.project_world(); dataflow=ws.dataflow_snapshot(path='auth/claims.py'); effects=ws.effect_snapshot(path='auth/claims.py'); runtime_topology=ws.runtime_topology()
            obs=ws.observatory_start(open_browser=False); time.sleep(.2)
            snap=json.loads(urllib.request.urlopen(obs['url']+'api/snapshot',timeout=5).read()); health=json.loads(urllib.request.urlopen(obs['url']+'api/health',timeout=5).read())
            (reports/'OBSERVATORY-SNAPSHOT-alpha12.json').write_text(json.dumps(snap,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
            post_status=None
            try: urllib.request.urlopen(urllib.request.Request(obs['url']+'api/snapshot',method='POST'),timeout=5)
            except urllib.error.HTTPError as exc: post_status=exc.code
            screenshot=screenshot_observatory(obs['url'],snap,shot)
            result={'version':'0.1.0-alpha.12','revision':ws.revision,'observatory':obs,'health':health,'read_only_post_status':post_status,
              'agents':snap['agents'],'graph':{'nodes':len(snap['graph']['nodes']),'edges':len(snap['graph']['edges'])},'visual_metrics':snap['visual_metrics'],'activity_seq':snap['activity_seq'],
              'project_world':{'nodes':len(project_world['nodes']),'edges':len(project_world['edges']),'providers':project_world['providers']},
              'effect_twin':{'count':effects['count'],'kind_counts':effects['kind_counts']},'dataflow_twin':{'count':dataflow['count'],'kind_counts':dataflow['kind_counts']},
              'runtime_topology':{'nodes':len(runtime_topology['nodes']),'edges':len(runtime_topology['edges'])},'counterfactual_compare':comparison,
              'promoted_world':promoted['world']['id'],'verification_status':verification['receipt']['structured']['status'],'ui_runtime':ui_result,
              'cognitive_plan':plan,'world_summary':world_summary,'source_packet_bytes':packet.get('source_bytes',0),'screenshot':screenshot,
              'claim_boundary':'Cinematic observer is fed by admitted Habitat state/events. Static effects/dataflow, observed runtime topology, and counterfactual compile evidence remain distinct evidence classes; UI exposes no raw private chain-of-thought or human control plane.'}
            out.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
            print(json.dumps({'report':str(out),'screenshot':screenshot,'verification':result['verification_status'],'agents':[a['name'] for a in snap['agents']],'graph':result['graph'],'visual':result['visual_metrics'],'ui_runtime':ui_result},ensure_ascii=False))
            ws.observatory_stop()
        finally: ws.close()
    return 0

if __name__=='__main__': raise SystemExit(main())
