from __future__ import annotations
import json, shutil, sys, tempfile, time, urllib.request, urllib.error, subprocess, os
from pathlib import Path

HERE=Path(__file__).resolve(); ROOT=HERE.parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from habitat.workspace import HabitatWorkspace
from habitat import shutdown_runtime_services
from habitat.mutation import TransactionConflict

RELEASE='0.1.0-alpha.13'

def screenshot_observatory(obs_url: str, snap: dict, shot: Path) -> dict:
    browser=shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome') or shutil.which('google-chrome-stable')
    if not browser: return {'captured':False,'reason':'Chromium unavailable'}
    args=[browser,'--headless=new','--disable-gpu','--disable-dev-shm-usage','--hide-scrollbars','--window-size=1920,1080',f'--screenshot={shot}','--virtual-time-budget=2800']
    if hasattr(os,'geteuid') and os.geteuid()==0: args.append('--no-sandbox')
    args.append(obs_url)
    try:
        proc=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        if proc.returncode==0 and shot.is_file() and shot.stat().st_size>10000:
            return {'captured':True,'path':shot.name,'bytes':shot.stat().st_size,'source':'live-http-chromium','dimensions':{'w':1920,'h':1080}}
    except Exception:
        pass
    # Exact live-snapshot fallback, no mock data.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b=pw.chromium.launch(headless=True,executable_path=browser,args=['--no-sandbox','--disable-dev-shm-usage'])
            page=b.new_page(viewport={'width':1920,'height':1080},device_scale_factor=1); assets=ROOT/'habitat'/'observatory_assets'
            html=(assets/'index.html').read_text(encoding='utf-8').replace('<link rel="stylesheet" href="/style.css">','').replace('<script src="/app.js"></script>','')
            page.set_content(html,wait_until='domcontentloaded'); page.add_style_tag(content=(assets/'style.css').read_text(encoding='utf-8'))
            page.evaluate('(payload)=>{window.__SNAPSHOT__=payload;window.fetch=async()=>new Response(JSON.stringify(window.__SNAPSHOT__),{status:200,headers:{"Content-Type":"application/json"}});window.EventSource=class{constructor(){this.listeners={};setTimeout(()=>{if(this.onopen)this.onopen({})},10)}addEventListener(k,fn){this.listeners[k]=fn}close(){}}}',snap)
            page.add_script_tag(content=(assets/'app.js').read_text(encoding='utf-8')); page.wait_for_timeout(1900); page.screenshot(path=str(shot),full_page=True); b.close()
        return {'captured':True,'path':shot.name,'bytes':shot.stat().st_size,'source':'live-snapshot-offline-render','dimensions':{'w':1920,'h':1080}}
    except Exception as exc:
        return {'captured':False,'reason':f'{type(exc).__name__}: {exc}'}

def main():
    reports=ROOT/'reports'; reports.mkdir(exist_ok=True)
    out=reports/'DEMO-EVIDENCE-alpha13.json'; snap_path=reports/'OBSERVATORY-SNAPSHOT-alpha13.json'; shot=reports/'OBSERVATORY-alpha13.png'
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); project=base/'project'; project.mkdir()
        for d in ['auth','billing','tests','ui','migrations','.github/workflows','services']:(project/d).mkdir(parents=True,exist_ok=True)
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
        # Enough low-value source to exercise server/client LOD truth disclosure.
        for i in range(150):
            (project/'services'/f'noise_{i:03d}.py').write_text(f'def noise_{i}(x):\n    y=x+{i}\n    return y\n',encoding='utf-8')
        (project/'package.json').write_text(json.dumps({'name':'nolane-demo','scripts':{'test':'python -m unittest','build':'vite'},'dependencies':{'express':'^5.0.0','pg':'^8.12.0'}},indent=2),encoding='utf-8')
        (project/'docker-compose.yml').write_text('services:\n  web:\n    image: demo/web\n    depends_on: [api]\n  api:\n    image: demo/api\n    depends_on: [db, redis]\n  db:\n    image: postgres:16\n  redis:\n    image: redis:7\n',encoding='utf-8')
        (project/'.github/workflows/ci.yml').write_text('jobs:\n  test:\n    runs-on: ubuntu-latest\n  build:\n    runs-on: ubuntu-latest\n',encoding='utf-8')
        (project/'openapi.json').write_text(json.dumps({'openapi':'3.1.0','info':{'title':'Auth API','version':'1'},'paths':{'/token/refresh':{'post':{'operationId':'refreshToken'}}}}),encoding='utf-8')
        (project/'migrations/001_users.sql').write_text('CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT,role TEXT,subscription_state TEXT);\n',encoding='utf-8')
        (project/'AGENTS.md').write_text('Auth changes require targeted verification. Observatory is human spectator only.\n',encoding='utf-8')
        (project/'ui/index.html').write_text('<!doctype html><html><body><button id="refreshBtn">Refresh token</button><div id="status">idle</div><script>document.getElementById("refreshBtn").onclick=()=>{document.getElementById("status").textContent="refreshed"}</script></body></html>',encoding='utf-8')

        ws=HabitatWorkspace.create(project,base/'habitat')
        try:
            codex=ws.agent_open('Codex',{'surface':'mcp','role':'implementer','task':'Fix expired subscription permissions'})['id']
            claude=ws.agent_open('Claude Code',{'surface':'mcp','role':'skeptic','task':'Challenge auth causality'})['id']
            verifier=ws.agent_open('Verifier Agent',{'surface':'direct','role':'verifier','task':'Discriminate counterfactual worlds'})['id']
            ctx=ws.orient('Fix expired subscription permissions during token refresh',budget=16,agent_id=codex)
            ep=ws.episode_start('Fix expired subscription permissions during token refresh',ctx.handle)
            ws.agent_residency_admit(codex,ctx.handle,max_admit=6,pin_top=2)
            addr=ws.context_address_space(ctx.handle,20); page_ids=[p['page_id'] for p in addr.get('pages',[])[:1]]
            if page_ids:
                ws.context_fetch_pages(ctx.handle,page_ids,8000); ws.context_fetch_pages(ctx.handle,page_ids,8000)  # deliberate refetch/thrash signal
            h1=ws.hypothesis_create('subscription freshness is lost before refresh-token claim construction',episode_id=ep['id'],prior_confidence=.70)
            h2=ws.hypothesis_create('claim builder elevates admin users without a fresh subscription guard',episode_id=ep['id'],prior_confidence=.55)
            ws.agent_belief_update(codex,h1['id'],stance='support',confidence=.79,rationale='static flow points toward freshness')
            ws.agent_belief_update(claude,h2['id'],stance='support',confidence=.68,rationale='claim guard is behaviorally decisive')
            ws.epistemic_create('unknown','whether refresh_token receives subscription state after revalidation',agent_id=codex,episode_id=ep['id'])
            ws.epistemic_create('contradiction','static input exists but fresh runtime state has not been demonstrated',agent_id=codex,episode_id=ep['id'])
            inv=ws.invariant_create('expired subscription must never produce elevated refreshed claims',severity='critical',metadata={'scope':'auth'})
            build_id=next(x['id'] for x in ws.store.symbols_named('build_claims') if x['path']=='auth/claims.py')
            ws.invariant_link(inv['id'],'symbol',build_id,relation='implements')
            first_mem=ws.memory_record('semantic','Expired subscriptions must produce non-elevated refreshed claims',confidence=.9,provenance={'source':'alpha13-demo'})
            echo_mem=ws.memory_record('semantic','Expired subscriptions must produce non-elevated refreshed claims',confidence=.9,provenance={'source':'alpha13-demo'})
            ws.effect_refresh(['auth/claims.py']); ws.dataflow_refresh(['auth/claims.py'])
            # Sensitive telemetry is intentionally injected; persistence/UI must redact it.
            ws.runtime_ingest('opentelemetry',[
                {'trace_id':'trace-refresh','span_id':'api','name':'POST /token/refresh','duration_ms':5.8,'attributes':{'service.name':'api','http.route':'/token/refresh','code.file.path':str(project/'auth/claims.py'),'code.line.number':12,'http.request.header.authorization':'Bearer TOPSECRET'}},
                {'trace_id':'trace-refresh','span_id':'db','parent_span_id':'api','name':'SELECT subscription','duration_ms':1.3,'attributes':{'service.name':'api','db.system':'postgresql','db.name':'users','db.statement':'SELECT * FROM users WHERE token=SECRET'}},
            ],agent_id=codex,episode_id=ep['id'])
            ws.runtime_ingest('dap',[{'session_id':'demo-debug','seq':10,'type':'event','event':'variables','body':{'variables':[{'name':'API_KEY','value':'sk-super-secret-demo-key'}]}}],agent_id=verifier,episode_id=ep['id'])
            # Exact replay should be idempotent after reconnect.
            dap_replay=ws.runtime_ingest('dap',[{'session_id':'demo-debug','seq':10,'type':'event','event':'variables','body':{'variables':[{'name':'API_KEY','value':'sk-super-secret-demo-key'}]}}],agent_id=verifier,episode_id=ep['id'])

            # Agent A observes a path; another agent will mutate it later, creating a real stale-cognition notification.
            ws.agent_observe(codex,'auth/claims.py')
            bad=ws.counterfactual_fork('WORLD A · unsafe elevation',agent_id=verifier)
            ws.counterfactual_apply(bad['id'],[{'op':'replace_text','path':'auth/claims.py','old':'elevated = bool(subscription_active and role == "admin")','new':'elevated = True'}])
            bad_verify=ws.counterfactual_verify(bad['id'])
            bad_promote_blocked=False
            try: ws.counterfactual_promote(bad['id'],agent_id=verifier,episode_id=ep['id'])
            except TransactionConflict: bad_promote_blocked=True
            good=ws.counterfactual_fork('WORLD B · explicit refresh gate',agent_id=claude)
            ws.counterfactual_apply(good['id'],[{'op':'replace_text','path':'auth/claims.py','old':'def refresh_token(subscription_active: bool, user):\n    return build_claims(subscription_active, user)','new':'def refresh_token(subscription_active: bool, user):\n    if not subscription_active:\n        return build_claims(False, user)\n    return build_claims(True, user)'}])
            good_verify=ws.counterfactual_verify(good['id'])
            promoted=ws.counterfactual_promote(good['id'],agent_id=claude,episode_id=ep['id'])
            verification=ws.verify(changed_paths=promoted['transaction'].get('changed_paths') or ['auth/claims.py'],episode_id=ep['id'])
            # Add a verifier link only after successful verification; before this it contributed to epistemic pressure.
            ws.invariant_link(inv['id'],'test','tests/test_auth.py',relation='verifier')
            ws.memory_record('experiment','WORLD B passed counterfactual and canonical targeted verification',agent_id=verifier,episode_id=ep['id'],confidence=.95,provenance={'source':'alpha13-demo'})
            # Re-ingest runtime evidence at current revision so static effects/dataflow can become observed-supported again.
            ws.runtime_ingest('opentelemetry',[{'trace_id':'trace-current','span_id':'api2','name':'POST /token/refresh verified','duration_ms':4.1,'attributes':{'service.name':'api','code.file.path':str(project/'auth/claims.py'),'code.line.number':14}}],agent_id=verifier,episode_id=ep['id'])
            # Visible repetitive operations create a loop-risk signal for the Verifier agent, not private-CoT inspection.
            for _ in range(9): ws.activity_emit('tool.started','tool',agent_id=verifier,episode_id=ep['id'],ref_id='workspace.inspect',status='running',summary='repeated inspect')
            # Browser UI actions are domain events when host supports Chromium.
            ui_result={'available':False}
            try:
                ui=ws.open_ui_runtime('ui/index.html'); ws.observe_ui_runtime(ui['session_id']); ws.act_ui_runtime(ui['session_id'],'click','ui:id:refreshBtn')
                assertion=ws.assert_ui_runtime(ui['session_id'],[{'handle':'ui:id:status','text_contains':'refreshed'}]); ws.close_ui_runtime(ui['session_id'])
                ui_result={'available':True,'assertion_passed':assertion.get('passed')}
            except Exception as exc:
                ws.activity_emit('ui.runtime-unavailable','ui',agent_id=verifier,episode_id=ep['id'],status='unavailable',summary='browser runtime unavailable',data={'error':f'{type(exc).__name__}: {exc}'})
                ui_result={'available':False,'reason':f'{type(exc).__name__}: {exc}'}
            shutdown_runtime_services()
            effects=ws.effect_snapshot(path='auth/claims.py'); dataflow=ws.dataflow_snapshot(path='auth/claims.py')
            health=ws.world_health(); c_health=ws.cognition_health(verifier); ctx_eff=ws.context_efficiency(ctx.handle)
            obs=ws.observatory_start(open_browser=False); time.sleep(.25)
            snap=json.loads(urllib.request.urlopen(obs['url']+'api/snapshot',timeout=6).read())
            snap_path.write_text(json.dumps(snap,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
            post_status=None
            try: urllib.request.urlopen(urllib.request.Request(obs['url']+'api/snapshot',method='POST'),timeout=5)
            except urllib.error.HTTPError as exc: post_status=exc.code
            screenshot=screenshot_observatory(obs['url'],snap,shot)
            runtime_blob=json.dumps(snap.get('runtime',[]),ensure_ascii=False)
            result={
                'version':RELEASE,'revision':ws.revision,'agents':len(snap.get('agents',[])),'activity_seq':snap.get('activity_seq'),
                'graph':{'nodes':len(snap['graph']['nodes']),'edges':len(snap['graph']['edges']),'sampling':snap['graph_sampling']},
                'visual_metrics':snap['visual_metrics'],'observer_health':snap['observer_health'],'world_health':health,'verifier_cognition_health':c_health,
                'context_efficiency':ctx_eff,'memory_echo_suppressed':first_mem['id']==echo_mem['id'] and bool(echo_mem.get('deduplicated_echo')),
                'dap_replay_ingested':dap_replay['ingested'],'telemetry_secret_absent':all(x not in runtime_blob for x in ['TOPSECRET','super-secret-demo-key','token=SECRET']),
                'bad_world':{'verification_status':bad_verify['status'],'promotion_blocked':bad_promote_blocked},
                'good_world':{'verification_status':good_verify['status'],'promoted':promoted['world']['id'],'canonical_verification':verification['receipt']['structured']['status']},
                'runtime_support':{'effect_counts':effects.get('runtime_support_counts'),'dataflow_counts':dataflow.get('runtime_support_counts')},
                'read_only_post_status':post_status,'ui_runtime':ui_result,'screenshot':screenshot,
                'claim_boundary':'Alpha13 resilience/cinematic demo uses explicit Habitat cognitive artifacts and admitted world events. Loop signals inspect visible operation repetition only; runtime support is correlation, not causality; Observatory is read-only and does not expose private chain-of-thought.'
            }
            out.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
            print(json.dumps({'report':str(out),'screenshot':screenshot,'tests':result['good_world'],'graph':result['graph'],'memory_echo':result['memory_echo_suppressed'],'secret_absent':result['telemetry_secret_absent'],'loop':c_health.get('loop'),'thrash':ctx_eff.get('refetch_ratio')},ensure_ascii=False))
            ws.observatory_stop()
        finally:
            ws.close(); shutdown_runtime_services()
    return 0

if __name__=='__main__': raise SystemExit(main())
