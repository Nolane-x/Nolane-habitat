from __future__ import annotations
import json, shutil, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path

HERE=Path(__file__).resolve(); ROOT=HERE.parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from habitat.workspace import HabitatWorkspace


def main():
    reports=ROOT/'reports'; reports.mkdir(exist_ok=True)
    out=reports/'OBSERVATORY-EVIDENCE-alpha11.json'; shot=reports/'OBSERVATORY-alpha11.png'
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); project=base/'project'; project.mkdir()
        (project/'auth').mkdir(); (project/'tests').mkdir(); (project/'billing').mkdir()
        (project/'auth'/'claims.py').write_text(
            'def build_claims(subscription_active: bool):\n'
            '    elevated = subscription_active\n'
            '    return {"elevated": elevated}\n\n'
            'def refresh_token(subscription_active: bool):\n'
            '    return build_claims(subscription_active)\n',encoding='utf-8')
        (project/'auth'/'subscription.py').write_text(
            'def is_active(state: str) -> bool:\n    return state not in {"expired", "cancelled"}\n',encoding='utf-8')
        (project/'billing'/'invoice.py').write_text('def total(amount):\n    return amount\n',encoding='utf-8')
        (project/'tests'/'test_auth.py').write_text(
            'import unittest\nfrom auth.claims import refresh_token\n\n'
            'class AuthTests(unittest.TestCase):\n'
            '    def test_expired_subscription(self):\n'
            '        self.assertFalse(refresh_token(False)["elevated"])\n\n'
            'if __name__ == "__main__": unittest.main()\n',encoding='utf-8')
        (project/'AGENTS.md').write_text('Run auth tests after changing claim behavior.\n',encoding='utf-8')
        ws=HabitatWorkspace.create(project,base/'habitat')
        try:
            codex=ws.agent_open('Codex',{'surface':'mcp','role':'implementer'})['id']
            claude=ws.agent_open('Claude Code',{'surface':'mcp','role':'skeptic'})['id']
            ctx=ws.orient('Fix expired subscription permissions during token refresh',budget=14,agent_id=codex)
            ep=ws.episode_start('Fix expired subscription permissions during token refresh',ctx.handle)
            ws.agent_residency_admit(codex,ctx.handle,max_admit=5,pin_top=1)
            packet=ws.context_prefetch(ctx.handle,max_source_bytes=6000,max_pages=5)
            h1=ws.hypothesis_create('subscription state is not rechecked during token refresh',episode_id=ep['id'],prior_confidence=.72)
            h2=ws.hypothesis_create('claim builder ignores the subscription state',episode_id=ep['id'],prior_confidence=.42)
            ws.agent_belief_update(codex,h1['id'],stance='support',confidence=.82,rationale='semantic path and task evidence align')
            ws.agent_belief_update(claude,h1['id'],stance='uncertain',confidence=.48,rationale='runtime observation still missing')
            ws.epistemic_create('unknown','whether refresh_token receives a freshly revalidated subscription state',agent_id=codex,episode_id=ep['id'])
            ws.epistemic_create('contradiction','static flow accepts subscription state but no runtime observation proves freshness',agent_id=codex,episode_id=ep['id'])
            ws.experiment_plan('observe refresh-token execution with an expired subscription',hypothesis_id=h1['id'],episode_id=ep['id'],discriminator='fresh state should produce elevated=false',capability='python.unittest')
            ws.runtime_ingest('opentelemetry',[
                {'trace_id':'trace-login-1','span_id':'span-refresh','name':'POST /token/refresh','status':{'code':'OK'},'duration_ms':4.3,
                 'attributes':{'code.file.path':str(project/'auth'/'claims.py'),'code.line.number':6,'http.route':'/token/refresh','habitat.episode.id':ep['id']}},
                {'trace_id':'trace-login-1','span_id':'span-claims','parent_span_id':'span-refresh','name':'ClaimsBuilder.build_claims','status':{'code':'OK'},'duration_ms':.7,
                 'attributes':{'code.file.path':str(project/'auth'/'claims.py'),'code.line.number':1}},
            ],agent_id=codex,episode_id=ep['id'])
            # A small exact mutation so activity/project graph actually pulses around a changed file.
            tx=ws.stage_change([{'op':'replace_text','path':'auth/claims.py','old':'elevated = subscription_active','new':'elevated = bool(subscription_active)'}],episode_id=ep['id'],agent_id=codex)
            committed=ws.commit_change(tx['id'],codex)
            verification=ws.verify(changed_paths=committed.get('changed_paths') or ['auth/claims.py'],episode_id=ep['id'])
            ws.experiment_complete(next(iter([r['id'] for r in ws.store.experiments_for_hypothesis(h1['id'])])),{'verification_status':verification['receipt']['structured']['status']})
            ws.memory_record('semantic','Expired subscriptions must produce non-elevated refreshed claims',episode_id=ep['id'],confidence=.96,provenance={'source':'targeted-verification','revision':ws.revision})
            ws.memory_record('episodic','The claims.py targeted mutation passed the expired-subscription verifier',agent_id=codex,episode_id=ep['id'],confidence=.9,provenance={'source':'work-episode'})
            ws.memory_record('decision','Keep Habitat Observatory observer-only; control remains on agent protocol/MCP',provenance={'source':'alpha11-architecture'})
            ws.runtime_ingest('opentelemetry',[
                {'record_type':'log','severity_text':'INFO','body':'expired subscription verifier passed','attributes':{'code.file.path':str(project/'tests'/'test_auth.py'),'code.line.number':5}},
                {'record_type':'metric','metric_name':'habitat.verification.passed','value':1,'unit':'1'}],agent_id=codex,episode_id=ep['id'])
            ws.activity_emit('agent.investigating','agent',agent_id=claude,episode_id=ep['id'],status='running',summary='checking alternative claim-builder explanation',data={'hypothesis_id':h2['id']})
            obs=ws.observatory_start(open_browser=False)
            # Give the server a moment and validate the real HTTP read model.
            time.sleep(.15)
            snap=json.loads(urllib.request.urlopen(obs['url']+'api/snapshot',timeout=5).read())
            health=json.loads(urllib.request.urlopen(obs['url']+'api/health',timeout=5).read())
            post_status=None
            try:
                urllib.request.urlopen(urllib.request.Request(obs['url']+'api/snapshot',method='POST'),timeout=5)
            except urllib.error.HTTPError as exc:
                post_status=exc.code
            screenshot={'captured':False,'reason':'playwright/browser unavailable'}
            browser=shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome') or shutil.which('google-chrome-stable')
            if browser:
                try:
                    from playwright.sync_api import sync_playwright
                    with sync_playwright() as pw:
                        b=pw.chromium.launch(headless=True,executable_path=browser,args=['--no-sandbox','--disable-dev-shm-usage'])
                        page=b.new_page(viewport={'width':1600,'height':1000},device_scale_factor=1)
                        try:
                            page.goto(obs['url'],wait_until='networkidle',timeout=10000)
                        except Exception:
                            # Some CI/browser policies block loopback navigation. Render the exact same UI
                            # against the already-fetched live snapshot rather than replacing it with mock data.
                            try: page.close()
                            except Exception: pass
                            page=b.new_page(viewport={'width':1600,'height':1000},device_scale_factor=1)
                            assets=ROOT/'habitat'/'observatory_assets'
                            html=(assets/'index.html').read_text(encoding='utf-8').replace('<link rel="stylesheet" href="/style.css">','').replace('<script src="/app.js"></script>','')
                            page.set_content(html,wait_until='domcontentloaded')
                            page.add_style_tag(content=(assets/'style.css').read_text(encoding='utf-8'))
                            page.evaluate('(payload)=>{ window.__SNAPSHOT__=payload; window.fetch=async()=>new Response(JSON.stringify(window.__SNAPSHOT__),{status:200,headers:{"Content-Type":"application/json"}}); window.EventSource=class { constructor(){this.listeners={};setTimeout(()=>{if(this.onopen)this.onopen({})},10)} addEventListener(k,fn){this.listeners[k]=fn} close(){} }; }',snap)
                            page.add_script_tag(content=(assets/'app.js').read_text(encoding='utf-8'))
                        page.wait_for_timeout(1100)
                        page.screenshot(path=str(shot),full_page=True); screenshot={'captured':True,'path':shot.name,'bytes':shot.stat().st_size,'source':'live-http' if page.url.startswith('http') else 'live-snapshot-offline-render'}
                        b.close()
                except Exception as exc:
                    screenshot={'captured':False,'reason':f'{type(exc).__name__}: {exc}'}
            result={
                'version':'0.1.0-alpha.11','revision':ws.revision,'observatory':obs,'health':health,'read_only_post_status':post_status,
                'agent_count':len(snap['agents']),'agent_names':[x['name'] for x in snap['agents']],
                'graph_nodes':len(snap['graph']['nodes']),'graph_edges':len(snap['graph']['edges']),
                'activity_seq':snap['activity_seq'],'hypotheses':len(snap['hypotheses']),'epistemic_items':len(snap['epistemic']),
                'runtime_events':len(snap['runtime']),'project_memories':len(snap.get('project_memory') or []),'context_memory':snap['context_memory'],'source_packet_bytes':packet.get('source_bytes',0),
                'verification_status':verification['receipt']['structured']['status'],'changed_paths':committed.get('changed_paths') or [],
                'cognitive_next':ws.cognition_next(codex,ep['id']),'semantic_fabric':ws.semantic_fabric(),'screenshot':screenshot,
                'claim_boundary':'Observer-only realtime projection of Habitat state and action summaries. It does not expose raw private model chain-of-thought and is not a human control plane.'
            }
            out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
            print(json.dumps({'report':str(out),'screenshot':screenshot,'verification':result['verification_status'],'agents':result['agent_names'],'activity_seq':result['activity_seq']},ensure_ascii=False))
        finally:
            ws.close()
    return 0

if __name__=='__main__': raise SystemExit(main())
