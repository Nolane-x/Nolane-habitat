const $=s=>document.querySelector(s);
const palette=['#22e9ff','#9b6cff','#ff43d1','#43ff9d','#ffd166','#4d88ff','#ff4e68','#29ffc6','#ff9d45'];
const typeColors={agent:'#22e9ff',file:'#355c9d',symbol:'#2fe6ff',hypothesis:'#9b6cff',epistemic:'#ff596f',memory:'#ff9d45',evidence:'#ffd166',runtime:'#ff43d1',episode:'#43ff9d',trajectory:'#7a6cff',milestone:'#5bffb0',transaction:'#4d88ff',effect:'#29ffc6',dataflow:'#00f5c8',counterfactual:'#b875ff',invariant:'#ffd166',service:'#36d8ff',database:'#ffbd55','message-bus':'#b65cff','runtime-route':'#ff4fd8','runtime-span':'#ff43d1','runtime-source':'#3b78cf','runtime-log':'#ffd166','runtime-metric':'#43ff9d',package:'#4d88ff','build-task':'#47b9ff','ci-workflow':'#9b6cff','ci-job':'#7259ff','api-spec':'#29ffc6','api-route':'#2dd5bb','api-operation':'#41ff9b','db-table':'#ffb85c','db-migration':'#ff865c','infra-resource':'#61d3ff','container-image':'#55bfff',build:'#4d88ff',port:'#ffd166'};
const categoryColors={source:'#22e9ff',mutation:'#4d88ff',verification:'#43ff9d',execution:'#ffd166',runtime:'#ff43d1',cognition:'#9b6cff',memory:'#ff9d45',coordination:'#ff596f',counterfactual:'#b875ff',effect:'#29ffc6',policy:'#ffd166',agent:'#22e9ff',observatory:'#43ff9d',ui:'#2fe6ff'};
let state={snapshot:null,seq:0,activities:[],pulses:new Map(),agentColors:new Map(),eventTimes:[],lastEvent:null,gap:false,operator:{mode:'world',manualUntil:0,sessionId:null,frameSeq:0,streamSeq:0,streamEpoch:null,streamMode:null,streamActive:false,streamPollBusy:false,pollHintMs:120,nextPollAt:0,generation:0,viewport:null,url:null,title:null,status:'idle',lastAction:null,timeline:[],queue:Promise.resolve(),cursor:{x:.5,y:.5}}};
const reducedMotion=matchMedia?.('(prefers-reduced-motion: reduce)')?.matches||false;
const colorForAgent=id=>{if(!state.agentColors.has(id))state.agentColors.set(id,palette[state.agentColors.size%palette.length]);return state.agentColors.get(id)};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function fmtTime(v){try{return new Date(v).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}catch{return '--:--:--'}}
function setHTML(sel,html){const n=$(sel);if(n)n.innerHTML=html}
function humanBytes(n){n=Number(n||0);if(n<1024)return `${n} B`;if(n<1048576)return `${(n/1024).toFixed(1)} KB`;return `${(n/1048576).toFixed(1)} MB`}
function short(s,n=50){s=String(s??'');return s.length>n?s.slice(0,n-1)+'…':s}
function statusColor(s){s=String(s||'').toLowerCase();return s.includes('fail')||s.includes('error')||s.includes('denied')?'#ff4e68':s.includes('pass')||s.includes('commit')||s.includes('fresh')||s.includes('complete')?'#43ff9d':s.includes('run')||s.includes('staged')||s.includes('pending')?'#ffd166':'#4d88ff'}
function isCdpStream(mode){return String(mode||'').startsWith('cdp-')}
function isContinuousStream(mode){return String(mode||'')==='cdp-websocket-live'}

function render(snapshot){
  state.snapshot=snapshot;
  $('#revision').textContent='REV '+(snapshot.revision||'—');
  $('#worldStats').textContent=`${snapshot.project.files} FILES · ${snapshot.project.symbols} SYMBOLS`;
  $('#backendState').textContent=(snapshot.backend?.kind||'backend')+' · '+(snapshot.execution_security?.sandboxed?'SANDBOXED':'OBSERVED');
  $('#graphCount').textContent=snapshot.graph?.nodes?.length||0;$('#effectCountTop').textContent=snapshot.effects?.length||0;$('#dataflowCountTop').textContent=snapshot.dataflows?.length||0;$('#runtimeCountTop').textContent=snapshot.runtime?.length||0;
  renderAgents(snapshot.agents||[]);renderProject(snapshot);renderCognition(snapshot);renderMemory(snapshot);renderSignals(snapshot);renderOperatorSnapshot(snapshot.operator||{});
  const lod=graph.setData(snapshot.graph||{nodes:[],edges:[]}),sampling=snapshot.graph_sampling||{};$('#lodTop').textContent=lod.hiddenNodes?`${lod.visibleNodes}/${lod.totalNodes}`:(sampling.bounded?`${lod.visibleNodes}+`:'FULL');$('#lodTop').title=sampling.bounded?'bounded observer read-model; project totals disclosed in snapshot':'full current observer graph';
  const oh=snapshot.observer_health||{},loop=oh.activity_loop||snapshot.cognitive_director?.loop||{},pressure=oh.epistemic_pressure||snapshot.cognitive_director?.pressure||{},mem=snapshot.context_memory||{};
  const degraded=['high','critical'].includes(String(pressure.level||'').toLowerCase())||['medium','high'].includes(String(loop.risk||'').toLowerCase())||state.gap;
  $('#healthTop').textContent=degraded?'DEGRADED':'OK';$('#loopTop').textContent=String(loop.risk||'none').toUpperCase();$('#thrashTop').textContent=`${Math.round(Number(mem.refetch_ratio||0)*100)}%`;
  renderActivitySnapshot(snapshot.activity||[],snapshot.activity_seq||0);renderDirector(snapshot);updateRate();
}
function renderAgents(agents){
  setHTML('#agentRail',agents.length?agents.map(a=>{const c=colorForAgent(a.id),h=a.health||{},hs=h.status||a.status||'active',meta=[];if(h.pending_invalidations)meta.push(`${h.pending_invalidations} stale`);if(h.loop&&h.loop.risk&&h.loop.risk!=='none')meta.push(`loop ${h.loop.risk}`);if(h.leases)meta.push(`${h.leases} lease`);const detail=[a.task||a.status||'connected',...meta].filter(Boolean).join(' · ');return `<div class="agent-chip ${hs==='stale'||hs==='loop-risk'?'warn':''}" style="--agent:${c}"><i class="orb"></i><div><b>${esc(a.name)}</b><small>${esc(detail)}</small></div><em>${esc(hs)}</em></div>`}).join(''):'<div class="agent-chip" style="--agent:#40516f"><i class="orb"></i><div><b>WAITING FOR AGENT</b><small>MCP / JSON / direct API ready</small></div><em>IDLE</em></div>');
}
function renderProject(s){
  const files=s.project?.files_view||[];
  setHTML('#projectWorld',files.slice(0,80).map(f=>`<div class="tree-row" data-path="${esc(f.path)}"><span>${esc(f.path)}</span><span class="lang">${esc(f.language)}</span></div>`).join(''));
  const entities=s.project_world?.nodes||[];
  setHTML('#worldEntities',entities.slice(0,15).map(e=>`<div class="entity-row" style="--entity:${typeColors[e.type]||'#4d88ff'}"><i></i><span>${esc(short(e.label,28))}</span><small>${esc(e.type)}</small></div>`).join('')||'<div class="entity-row"><i></i><span>no manifest-world entities</span><small>idle</small></div>');
  const worlds=s.counterfactual_worlds||[];
  setHTML('#worldForks',worlds.slice(0,8).map(w=>{const wc=w.verification_status==='failed'?'#ff4e68':w.verification_status==='stale'?'#ffd166':w.status==='open'?'#b875ff':'#43ff9d';return `<div class="entity-row" style="--entity:${wc}"><i></i><span>${esc(short(w.label,26))}</span><small>${esc(w.status)} · ${esc(w.verification_status||'never')} · ${w.change_count||0}</small></div>`}).join('')||'<div class="entity-row"><i></i><span>canonical world only</span><small>1 WORLD</small></div>');
}
function renderCognition(s){
  const ep=(s.episodes||[]).find(x=>x.status!=='completed')||(s.episodes||[])[0],agent=(s.agents||[]).find(a=>a.status==='active')||(s.agents||[])[0],tr=(s.executive?.trajectories||[]).find(x=>x.status==='active')||(s.executive?.trajectories||[])[0];
  const task=tr?.goal||ep?.task||agent?.task||'Waiting for an agent task…';let meta=[];if(tr){meta.push('TR '+tr.id.slice(0,10));meta.push('STRATEGY '+String(tr.current_strategy||'direct-analysis').toUpperCase())}if(ep)meta.push('EP '+ep.id.slice(0,10));if(agent)meta.push(agent.name);meta.push('rev '+String(s.revision).slice(0,14));
  setHTML('#taskCard',`<div class="task">${esc(task)}</div><div class="task-meta">${meta.map(x=>`<span>${esc(x)}</span>`).join('')}</div>`);$('#cognitiveState').textContent=(tr?.status||ep?.status||'observing').toUpperCase();
  const hy=s.hypotheses||[];setHTML('#hypotheses',hy.length?hy.slice(0,5).map(h=>`<div class="card"><div>${esc(h.statement)}</div><div class="meta">${esc(h.status)} · <span class="confidence">belief annotation ${Number(h.current_confidence??h.confidence??0).toFixed(2)}</span></div></div>`).join(''):'<div class="card"><div>No active hypothesis recorded</div><div class="meta">Habitat does not invent private reasoning.</div></div>');
  const epi=s.epistemic||[];setHTML('#epistemic',epi.length?epi.slice(0,7).map(x=>`<div class="card ${esc(x.kind)}"><div>${esc(x.statement)}</div><div class="meta">${esc(x.kind)} · ${esc(x.status)}${x.base_revision!==s.revision?' · STALE':''}</div></div>`).join(''):'<div class="card unknown"><div>No explicit unknown / contradiction recorded</div></div>');
  const inv=(s.invariants||[]).slice(0,3),pending=s.coordination?.pending||[],leases=s.coordination?.leases||[];
  let rows=inv.map(x=>`<div class="card" style="border-left-color:#ffd166"><div>${esc(x.statement)}</div><div class="meta">invariant · ${esc(x.status)} · ${esc(x.severity)}</div></div>`);
  if(pending.length)rows.push(`<div class="card contradiction"><div>${pending.length} stale-cognition notification${pending.length>1?'s':''}</div><div class="meta">selective revalidation required</div></div>`);
  if(leases.length)rows.push(`<div class="card assumption"><div>${leases.length} active mutation lease${leases.length>1?'s':''}</div><div class="meta">multi-agent coordination</div></div>`);
  setHTML('#invariantCoord',rows.join('')||'<div class="card"><div>No active invariant/coordination alert</div><div class="meta">world stable</div></div>');
}
function renderDirector(s){const d=s.cognitive_director||{},n=d.next||{},tr=(s.executive?.trajectories||[]).find(x=>x.status==='active');$('#directorOp').textContent=String(n.operation||'observing').toUpperCase().replaceAll('-',' ');$('#directorReason').textContent=(tr?`[${String(tr.current_strategy||'direct-analysis').toUpperCase()}] `:'')+(n.reason||'waiting for the next machine-world transition');$('#directorInfo').textContent='INFO '+String(n.information_gain||'—').toUpperCase();$('#directorCost').textContent='COST '+String(n.cost||'—').toUpperCase();$('#debtValue').textContent=d.epistemic_debt??0;const rt=s.runtime_topology||{},pw=s.project_world||{};const gs=s.graph_sampling||{};$('#worldTopologyStats').textContent=`${s.graph?.edges?.length||0} LINKS · ${rt.edges?.length||0} RUNTIME FLOWS · ${pw.nodes?.length||0} WORLD ENTITIES${gs.bounded?' · BOUNDED VIEW':''}`}
function renderMemory(s){const mem=s.context_memory||{},rows=mem.residents||[],long=s.project_memory||[];$('#memoryBudget').textContent=`${humanBytes(mem.agent_visible_source_bytes)} PAGED · ${humanBytes(mem.authority_bytes_read)} IO · ${long.filter(x=>x.status==='active').length} MEM`;let hot=rows.slice(0,13).map((r,i)=>`<div class="memory-item ${i<4?'hot':''}"><i class="heat"></i><span>${esc(short(r.label||r.object_id||r.path,30))}</span><small>${r.pinned?'PIN':'resident'}</small></div>`).join('');let durable=long.slice(0,8).map(r=>`<div class="memory-item ${r.status==='active'&&!r.revision_drift?'':'stale'}"><i class="heat"></i><span>${esc(short(r.statement,36))}</span><small>${esc(r.kind)} · ${r.revision_drift?'STALE':esc(r.status)}</small></div>`).join('');setHTML('#memory',(hot||'<div class="memory-item"><i class="heat"></i><span>No resident context yet</span><small>cold</small></div>')+(durable?'<div class="section-label">PROJECT MEMORY · PROVENANCE BOUND</div>'+durable:''))}
function renderSignals(s){
  const effects=(s.effects||[]).slice(0,18).map(e=>({kind:'effect',type:e.kind,name:e.target,path:e.path,status:e.trust,color:e.runtime_support?.observed?'#54ffd5':'#29ffc6',detail:`L${e.line||'?'} · ${e.trust}${e.runtime_support?.observed?' · RT '+String(e.runtime_support.grade).toUpperCase():''}`}));
  const runtime=(s.runtime||[]).slice(0,18).map(r=>({kind:'runtime',type:r.kind,name:r.name,path:r.path,status:r.status,color:'#ff43d1',detail:r.duration_ms!=null?`${Number(r.duration_ms).toFixed(1)} ms`:r.source}));
  const merged=[];for(let i=0;i<Math.max(effects.length,runtime.length);i++){if(runtime[i])merged.push(runtime[i]);if(effects[i])merged.push(effects[i])}
  $('#signalCount').textContent=`${merged.length} SIGNALS`;setHTML('#signals',merged.slice(0,26).map(x=>`<div class="signal-row" style="--sig:${x.color}"><i></i><span>${esc(x.type)}</span><b>${esc(short(x.name,58))}</b><small>${esc(x.detail||x.status||'')}</small><div class="meter"></div></div>`).join('')||'<div class="signal-row" style="--sig:#40516f"><i></i><span>idle</span><b>waiting for effects/runtime</b><small>—</small></div>');
}
function evtColor(e){return categoryColors[e.category]||statusColor(e.status)}
function renderActivitySnapshot(events,seq){state.seq=Math.max(state.seq,seq||0);state.activities=[...events].reverse().slice(0,220);state.eventTimes=state.activities.map(x=>Date.parse(x.created_at)||0).filter(Boolean);$('#activitySeq').textContent='SEQ '+state.seq;setHTML('#activity',state.activities.slice(0,70).map(e=>`<div class="activity-row" style="--evt:${evtColor(e)}"><time>${fmtTime(e.created_at)}</time><b>${esc(e.summary||e.kind)}</b>${e.path?`<br><code>${esc(e.path)}</code>`:''}</div>`).join('')||'<div class="activity-row"><b>No activity yet</b></div>');updateRate()}
let activityRenderPending=false;
function scheduleActivityRender(){if(activityRenderPending)return;activityRenderPending=true;requestAnimationFrame(()=>{activityRenderPending=false;$('#activitySeq').textContent='SEQ '+state.seq;setHTML('#activity',state.activities.slice(0,70).map((e,i)=>`<div class="activity-row ${i===0?'flash':''}" style="--evt:${evtColor(e)}"><time>${fmtTime(e.created_at)}</time><b>${esc(e.summary||e.kind)}</b>${e.path?`<br><code>${esc(e.path)}</code>`:''}</div>`).join(''));updateRate()})}
function activity(event){
  state.seq=Math.max(state.seq,event.seq||0);state.activities.unshift(event);state.activities=state.activities.slice(0,220);state.eventTimes.unshift(Date.now());state.eventTimes=state.eventTimes.filter(t=>Date.now()-t<30000);state.lastEvent=event;scheduleActivityRender();operatorActivity(event);
  if(event.path){document.querySelectorAll('.tree-row.hot').forEach(n=>n.classList.remove('hot'));let n=[...document.querySelectorAll('.tree-row')].find(x=>x.dataset.path===event.path);if(n)n.classList.add('hot')}
  let key=event.ref_id||event.path||event.agent_id;if(key)state.pulses.set(key,performance.now()+2600);graph.pulse(key);graph.spawnEvent(event);$('#worldPulseText').textContent=short(event.summary||event.kind,90);if(String(event.status||'').match(/fail|error|denied/i)){let s=$('#shockFlash');s.classList.remove('error');void s.offsetWidth;s.classList.add('error')};updateRate();
}
function updateRate(){const now=Date.now();state.eventTimes=state.eventTimes.filter(t=>now-t<10000);$('#eventRate').textContent=(state.eventTimes.length/10).toFixed(1)}
async function snapshot(){try{const r=await fetch('/api/snapshot',{cache:'no-store'});if(!r.ok)throw Error(r.status);render(await r.json());$('#liveDot').className='dot live';$('#connection').textContent='LIVE'}catch(e){$('#liveDot').className='dot';$('#connection').textContent='RECONNECTING'}}
function connect(){const es=new EventSource('/events?since='+state.seq);es.addEventListener('activity',e=>{try{activity(JSON.parse(e.data))}catch{}});es.addEventListener('gap',async e=>{state.gap=true;$('#connection').textContent='RESYNCING';try{await snapshot();state.gap=false}catch{}});es.onopen=()=>{$('#liveDot').className='dot live';$('#connection').textContent=state.gap?'RESYNCING':'LIVE'};es.onerror=()=>{$('#connection').textContent='RECONNECTING';es.close();setTimeout(connect,900)}}


const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function setStageMode(mode,{manual=false}={}){
  if(!['world','operator','split'].includes(mode))mode='world';
  state.operator.mode=mode;if(manual)state.operator.manualUntil=Date.now()+30000;
  const stage=$('#stage');stage.classList.remove('stage-world','stage-operator','stage-split');stage.classList.add('stage-'+mode);
  document.querySelectorAll('.stage-tab').forEach(b=>{const active=b.dataset.stage===mode;b.classList.toggle('active',active);b.setAttribute('aria-selected',active?'true':'false')});
  $('#stageTitle').textContent=mode==='world'?'HABITAT WORLD MAP':mode==='operator'?'AI OPERATOR / LIVE SOFTWARE MIRROR':'WORLD + AI OPERATOR';
  $('#mapLegend').textContent=mode==='world'?'SEMANTIC · EFFECT · RUNTIME · COGNITIVE':mode==='operator'?'AUTHORITATIVE PLAYWRIGHT FRAME · SEMANTIC POINTER':'DUAL OBSERVABILITY';
  setTimeout(()=>graph.resize(),80);
}
function autoOperatorFocus(){if(Date.now()>state.operator.manualUntil&&state.operator.sessionId)setStageMode('operator')}
document.querySelectorAll('.stage-tab').forEach(b=>{b.addEventListener('click',()=>setStageMode(b.dataset.stage,{manual:true}));b.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setStageMode(b.dataset.stage,{manual:true})}})});

function adoptOperatorSession(sessionId,streamEpoch=null){
  if(!sessionId)return false;const epochChanged=!!(streamEpoch&&state.operator.streamEpoch&&streamEpoch!==state.operator.streamEpoch),sessionChanged=sessionId!==state.operator.sessionId;
  if(!sessionChanged&&!epochChanged){if(streamEpoch)state.operator.streamEpoch=streamEpoch;return false}
  state.operator.generation++;state.operator.sessionId=sessionId;state.operator.frameSeq=0;state.operator.streamSeq=0;state.operator.streamEpoch=streamEpoch||null;state.operator.streamMode=null;state.operator.streamActive=false;state.operator.pollHintMs=120;state.operator.nextPollAt=0;state.operator.lastAction=null;state.operator.timeline=[];
  const img=$('#operatorFrame');img.classList.remove('loaded');img.removeAttribute('src');$('#operatorEmpty').classList.remove('hidden');$('#targetBox').classList.remove('visible');$('#aiCursor').classList.remove('visible');$('#typingGhost').classList.remove('visible');setHTML('#operatorTimeline','');$('#operatorFrameSeq').textContent='FRAME 0';$('#operatorSession').textContent=short(sessionId,17);$('#operatorStream').textContent='SYNCING';
  return true;
}
function operatorFrameUrl(sessionId,seq){return `/api/ui-frame?session_id=${encodeURIComponent(sessionId)}&seq=${encodeURIComponent(String(seq||0))}&v=${encodeURIComponent(String(seq||0))}`}
function setOperatorFrame(sessionId,seq,streamEpoch=null){
  if(!sessionId)return;adoptOperatorSession(sessionId,streamEpoch);const next=Number(seq||0);if(!Number.isFinite(next)||next<=0||next<state.operator.frameSeq)return;const img=$('#operatorFrame');state.operator.frameSeq=next;
  $('#operatorFrameSeq').textContent='FRAME '+state.operator.frameSeq;$('#operatorSession').textContent=short(sessionId,17);
  img.onload=()=>{if(sessionId!==state.operator.sessionId)return;img.classList.add('loaded');$('#operatorEmpty').classList.add('hidden');reprojectOperatorOverlays()};
  img.onerror=()=>{if(sessionId!==state.operator.sessionId)return;if(!img.classList.contains('loaded'))$('#operatorEmpty').classList.remove('hidden')};
  img.src=operatorFrameUrl(sessionId,state.operator.frameSeq);
}
function applyOperatorStream(meta){
  if(!meta?.session_id)return;adoptOperatorSession(meta.session_id,meta.stream_epoch||null);if(meta.session_id!==state.operator.sessionId)return;
  if(meta.stream_epoch&&state.operator.streamEpoch&&meta.stream_epoch!==state.operator.streamEpoch)return;
  state.operator.streamEpoch=meta.stream_epoch||state.operator.streamEpoch;state.operator.streamSeq=Math.max(Number(state.operator.streamSeq||0),Number(meta.stream_seq||0));state.operator.streamMode=meta.stream_mode||state.operator.streamMode;state.operator.streamActive=!!meta.stream_active;const hint=Number(meta.poll_hint_ms||0);if(Number.isFinite(hint)&&hint>0)state.operator.pollHintMs=Math.max(50,Math.min(1000,hint));
  const label=isCdpStream(state.operator.streamMode)?(state.operator.streamActive?(isContinuousStream(state.operator.streamMode)?'CDP LIVE':'CDP SYNC'):'CDP PAUSED'):'SNAPSHOT';$('#operatorStream').textContent=label;$('#operatorStream').className=state.operator.streamActive?'live':'fallback';
  if(Number(meta.frame_seq||0)>state.operator.frameSeq)setOperatorFrame(meta.session_id,meta.frame_seq,state.operator.streamEpoch);
}
async function pollOperatorStream(){
  const sid=state.operator.sessionId,now=Date.now();if(!sid||document.hidden||['closed','idle'].includes(String(state.operator.status||'')))return;if(now<Number(state.operator.nextPollAt||0)||state.operator.streamPollBusy)return;state.operator.streamPollBusy=true;state.operator.nextPollAt=now+Number(state.operator.pollHintMs||120);
  try{const r=await fetch(`/api/ui-stream?session_id=${encodeURIComponent(sid)}`,{cache:'no-store'});if(!r.ok)return;const meta=await r.json();if(sid!==state.operator.sessionId)return;applyOperatorStream(meta)}catch{}finally{state.operator.streamPollBusy=false;state.operator.nextPollAt=Math.max(Number(state.operator.nextPollAt||0),Date.now()+Number(state.operator.pollHintMs||120))}
}
// A cheap scheduler tick respects the transport-provided poll hint, so snapshot fallback does not
// hammer the read-only HTTP surface at the cadence intended for continuous CDP.
setInterval(pollOperatorStream,50);
function renderOperatorSnapshot(op){
  if(!op)return;const sid=op.session_id||state.operator.sessionId;
  if(sid){adoptOperatorSession(sid,op.stream_epoch||null);state.operator.viewport=op.viewport||state.operator.viewport;state.operator.url=op.url||op.target||state.operator.url;state.operator.title=op.title||state.operator.title;state.operator.status=op.status||'live';state.operator.streamMode=op.stream_mode||state.operator.streamMode;state.operator.streamActive=!!op.stream_active;state.operator.streamSeq=Math.max(Number(state.operator.streamSeq||0),Number(op.stream_seq||0));
    $('#operatorUrl').textContent=state.operator.url||op.target||'local runtime';$('#operatorTitle').textContent=state.operator.title||'AI BROWSER RUNTIME';
    const vp=state.operator.viewport||{};$('#operatorViewportSize').textContent=vp.width&&vp.height?`${vp.width} × ${vp.height}`:'— × —';
    if(Number(op.frame_seq||0)>state.operator.frameSeq||!$('#operatorFrame').classList.contains('loaded'))setOperatorFrame(sid,op.frame_seq||state.operator.frameSeq||1,state.operator.streamEpoch);
    if(op.last_action){state.operator.lastAction=op.last_action;renderOperatorAction(op.last_action,false)}
    $('#operatorStream').textContent=isCdpStream(state.operator.streamMode)?(state.operator.streamActive?(isContinuousStream(state.operator.streamMode)?'CDP LIVE':'CDP SYNC'):'CDP PAUSED'):'SNAPSHOT';
    if(String(op.status||'live')!=='closed')autoOperatorFocus();
  }
  updateOperatorState(op.status||state.operator.status||'idle');
}
function updateOperatorState(status){
  status=String(status||'idle').toLowerCase();state.operator.status=status;$('#operatorState').textContent=status.toUpperCase();$('#operatorTop').textContent=status==='closed'?'OFF':status.toUpperCase();$('#operatorTop').className=status;
  $('#operatorProtocol').textContent=status==='acting'?'AI INPUT':isCdpStream(state.operator.streamMode)?(isContinuousStream(state.operator.streamMode)?'CDP LIVE MIRROR':'CDP MIRROR'):'AI VIEW';
}

function displayedViewportBox(){
  const host=$('#operatorViewport').getBoundingClientRect(),vp=state.operator.viewport||{},vw=Number(vp.width||$('#operatorFrame').naturalWidth||host.width),vh=Number(vp.height||$('#operatorFrame').naturalHeight||host.height);
  const scale=Math.min(host.width/Math.max(1,vw),host.height/Math.max(1,vh)),w=vw*scale,h=vh*scale;
  return{x:(host.width-w)/2,y:(host.height-h)/2,w,h,scale,vw,vh};
}
function projectPoint(pointer){const b=displayedViewportBox();let nx=Number(pointer?.nx),ny=Number(pointer?.ny);if(!Number.isFinite(nx))nx=Number(pointer?.x||0)/Math.max(1,b.vw);if(!Number.isFinite(ny))ny=Number(pointer?.y||0)/Math.max(1,b.vh);return{x:b.x+Math.max(0,Math.min(1,nx))*b.w,y:b.y+Math.max(0,Math.min(1,ny))*b.h}}
function projectRect(rect){if(!rect)return null;const b=displayedViewportBox();return{x:b.x+Number(rect.x||0)*b.scale,y:b.y+Number(rect.y||0)*b.scale,width:Math.max(2,Number(rect.width||0)*b.scale),height:Math.max(2,Number(rect.height||0)*b.scale)}}
function reprojectOperatorOverlays(){const a=state.operator.lastAction;if(!a)return;positionOperatorTarget(a);positionCursor(a.pointer)}
addEventListener('resize',()=>setTimeout(reprojectOperatorOverlays,60));
function positionCursor(pointer){if(!pointer)return;const p=projectPoint(pointer),c=$('#aiCursor'),first=!c.classList.contains('visible');state.operator.cursor={x:p.x,y:p.y};if(first)c.style.transition='none';c.style.left=p.x+'px';c.style.top=p.y+'px';c.classList.add('visible');if(first){void c.offsetWidth;requestAnimationFrame(()=>c.style.transition='')}$('#operatorPointer').textContent=`${Math.round(Number(pointer.x||0))}, ${Math.round(Number(pointer.y||0))}`}
function positionOperatorTarget(a){const rect=projectRect(a?.target?.rect),box=$('#targetBox');if(!rect){box.classList.remove('visible');return}box.style.left=rect.x+'px';box.style.top=rect.y+'px';box.style.width=rect.width+'px';box.style.height=rect.height+'px';box.classList.add('visible');$('#targetLabel').textContent=String(a.action||'target').toUpperCase()}
function operatorIntent(a){if(!a)return 'No UI action yet.';const t=a.target||{},name=t.name||t.attrs?.['aria-label']||t.attrs?.placeholder||t.role||t.tag||a.handle||'element',action=String(a.action||'inspect').toUpperCase();if(a.value_redacted)return `${action} ${name} · sensitive value redacted`;if(a.value_preview!=null&&a.value_preview!=='')return `${action} ${name} ← “${short(a.value_preview,52)}”`;return `${action} ${name}`}
function renderOperatorAction(a,hot=true){
  if(!a)return;state.operator.lastAction=a;const t=a.target||{},name=t.name||t.attrs?.placeholder||t.role||t.tag||a.handle||'—';
  $('#operatorTarget').textContent=short(name,34);$('#operatorHandle').textContent=short(a.handle||'no semantic handle',42);$('#operatorActionKind').textContent=String(a.action||'—').toUpperCase();$('#operatorIntent').textContent=operatorIntent(a);
  const d=a.delta_counts||{};$('#operatorDelta').textContent=`${d.added||0} / ${d.removed||0} / ${d.changed||0}`;$('#operatorNetwork').textContent=a.network_count??0;$('#operatorConsole').textContent=a.console_count??0;$('#operatorLayout').textContent=a.layout_issue_count??0;
  positionOperatorTarget(a);positionCursor(a.pointer);if(hot)appendOperatorTick(a);
}
function appendOperatorTick(a){const row={time:new Date(),text:operatorIntent(a)};state.operator.timeline.unshift(row);state.operator.timeline=state.operator.timeline.slice(0,7);setHTML('#operatorTimeline',state.operator.timeline.map((x,i)=>`<div class="operator-tick ${i===0?'hot':''}"><time>${fmtTime(x.time)}</time><b>${esc(x.text)}</b></div>`).join(''))}
async function animateTyping(a){
  if(!['fill','press'].includes(String(a.action||''))||a.value_preview==null)return;const ghost=$('#typingGhost'),txt=$('#typingText');let value=a.value_redacted?'•'.repeat(Math.min(24,Math.max(4,Number(a.value_length||8)))):String(a.value_preview||'');ghost.classList.add('visible');txt.textContent='';
  const chars=[...value],step=Math.max(16,Math.min(55,550/Math.max(1,chars.length)));for(let i=0;i<chars.length;i++){txt.textContent+=chars[i];await sleep(step)}await sleep(160);ghost.classList.remove('visible');
}
function clickPulseAt(a){if(!a?.pointer)return;const p=projectPoint(a.pointer),pulse=$('#clickPulse'),cursor=$('#aiCursor');pulse.style.left=p.x+'px';pulse.style.top=p.y+'px';pulse.classList.remove('fire');void pulse.offsetWidth;pulse.classList.add('fire');cursor.classList.add('clicking');setTimeout(()=>cursor.classList.remove('clicking'),120)}
function queueOperatorStart(a,sessionId){
  if(sessionId)adoptOperatorSession(sessionId);const gen=state.operator.generation;
  state.operator.queue=state.operator.queue.then(async()=>{if(gen!==state.operator.generation)return;autoOperatorFocus();updateOperatorState('acting');renderOperatorAction(a,true);$('#operatorAction').textContent=`AI / ${String(a.action||'ACTION').toUpperCase()} / ${short(a.target?.name||a.handle||'',36)}`;await sleep(reducedMotion?30:430);if(gen!==state.operator.generation)return;if(['click','double-click','check','uncheck','select'].includes(String(a.action||'')))clickPulseAt(a);await animateTyping(a);if(gen!==state.operator.generation)return;await sleep(reducedMotion?20:120)}).catch(()=>{});
}
function queueOperatorComplete(a,sessionId,frameSeq,status,streamEpoch=null){
  if(sessionId)adoptOperatorSession(sessionId,streamEpoch);const gen=state.operator.generation;
  state.operator.queue=state.operator.queue.then(async()=>{if(gen!==state.operator.generation)return;if(a){renderOperatorAction(a,false);if(['click','double-click'].includes(String(a.action||'')))clickPulseAt(a)}const failed=['failed','error'].includes(String(status||'').toLowerCase());updateOperatorState(failed?'error':'live');if(sessionId&&frameSeq)setOperatorFrame(sessionId,frameSeq,streamEpoch);$('#operatorAction').textContent=failed?'AI ACTION FAILED':'AI ACTION COMMITTED / STREAM SYNCED';await sleep(reducedMotion?20:180)}).catch(()=>{});
}
function operatorActivity(e){
  const kind=String(e?.kind||''),d=e?.data||{};if(!kind.startsWith('ui.'))return;
  const sid=d.session_id||(kind==='ui.runtime-opened'||kind==='ui.runtime-observed'||kind==='ui.runtime-closed'?e.ref_id:null);if(sid)adoptOperatorSession(sid,d.operator_stream_epoch||null);
  if(d.viewport)state.operator.viewport=d.viewport;if(d.url||d.target)state.operator.url=d.url||d.target;if(d.title)state.operator.title=d.title;if(d.operator_stream_mode)state.operator.streamMode=d.operator_stream_mode;if(d.operator_stream_seq!=null)state.operator.streamSeq=Math.max(Number(state.operator.streamSeq||0),Number(d.operator_stream_seq||0));if(d.operator_stream_active!=null)state.operator.streamActive=!!d.operator_stream_active;
  if(state.operator.url)$('#operatorUrl').textContent=state.operator.url;if(state.operator.title)$('#operatorTitle').textContent=state.operator.title;const vp=state.operator.viewport||{};if(vp.width&&vp.height)$('#operatorViewportSize').textContent=`${vp.width} × ${vp.height}`;
  if(kind==='ui.runtime-opened'){updateOperatorState('live');autoOperatorFocus();setOperatorFrame(sid,d.operator_frame_seq||1,d.operator_stream_epoch||null);$('#operatorAction').textContent='AI OPENED SOFTWARE / CDP STREAM ATTACHED';pollOperatorStream();return}
  if(kind==='ui.runtime-observed'){updateOperatorState('live');if(sid&&d.operator_frame_seq)setOperatorFrame(sid,d.operator_frame_seq,d.operator_stream_epoch||null);return}
  if(kind==='ui.runtime-closed'){state.operator.streamActive=false;updateOperatorState('closed');$('#operatorStream').textContent='CLOSED';$('#operatorAction').textContent='UI RUNTIME CLOSED';return}
  if(kind==='ui.action-started'){const a=d.action_preview||{action:d.action,handle:d.handle};queueOperatorStart(a,sid);return}
  if(kind==='ui.action-completed'){const a=d.action_receipt||d.action_preview||{action:d.action,handle:d.handle};queueOperatorComplete(a,sid,d.operator_frame_seq||a.frame_seq,String(e.status||''),d.operator_stream_epoch||a.stream_epoch||null);return}
}

function hash(s){let h=2166136261;for(let i=0;i<String(s).length;i++){h^=String(s).charCodeAt(i);h=Math.imul(h,16777619)}return h>>>0}
function nodeColor(n){if(n.type==='agent')return colorForAgent(n.id);if(n.type==='epistemic')return n.kind==='unknown'?'#ffd166':'#ff596f';return typeColors[n.type]||'#60789b'}
function edgeColor(k){k=String(k||'');if(k.includes('runtime')||k.includes('span')||k.includes('db-'))return'#ff43d1';if(k.includes('dataflow'))return'#00f5c8';if(k.includes('effect'))return'#29ffc6';if(k.includes('evidence'))return'#ffd166';if(k.includes('hypothesis')||k.includes('cognition'))return'#9b6cff';if(k.includes('world')||k.includes('counter'))return'#b875ff';if(k.includes('call')||k.includes('import'))return'#22e9ff';return'#5674a1'}

function eventPriority(e){const st=String(e?.status||'').toLowerCase(),k=String(e?.kind||'').toLowerCase(),c=String(e?.category||'').toLowerCase();if(/fail|error|denied|conflict/.test(st))return 5;if(/commit|verification|promot|rollback/.test(k))return 4;if(c==='runtime'||c==='mutation'||c==='counterfactual'||c==='coordination')return 3;if(c==='cognition'||c==='ui')return 2;return 1}
function compressGraph(g,maxNodes=420,maxEdges=900){
  const all=[...(g.nodes||[])],edges=[...(g.edges||[])];if(all.length<=maxNodes){const ee=edges.slice(0,maxEdges);return{nodes:all,edges:ee,totalNodes:all.length,hiddenNodes:0,totalEdges:edges.length,hiddenEdges:Math.max(0,edges.length-ee.length)}};
  const deg=new Map();for(const e of edges){deg.set(e.source,(deg.get(e.source)||0)+1);deg.set(e.target,(deg.get(e.target)||0)+1)}
  const hot=new Set();for(const e of (state.activities||[]).slice(0,60)){if(e.ref_id)hot.add(e.ref_id);if(e.path)hot.add(e.path);if(e.agent_id)hot.add(e.agent_id)}
  const weight={agent:150,trajectory:145,milestone:128,hypothesis:135,epistemic:135,evidence:125,counterfactual:125,invariant:122,episode:115,transaction:112,service:110,database:110,'message-bus':106,'runtime-span':105,'runtime-log':102,'runtime-metric':102,runtime:104,effect:92,dataflow:92,memory:88,file:75,symbol:65};
  const score=n=>(weight[n.type]||55)+(hot.has(n.id)||hot.has(n.path)||hot.has(n.agent_id)?180:0)+Math.min(50,(deg.get(n.id)||0)*2)+(String(n.status||'').match(/fail|error|stale|conflict/i)?45:0);
  const ranked=all.slice().sort((a,b)=>score(b)-score(a));const reserve=28,keep=ranked.slice(0,Math.max(1,maxNodes-reserve));const kept=new Set(keep.map(n=>n.id));const omitted=all.filter(n=>!kept.has(n.id));
  const groups=new Map();for(const n of omitted){const t=n.type||'other';if(!groups.has(t))groups.set(t,[]);groups.get(t).push(n)}
  const clusters=[];const remap=new Map();for(const n of keep)remap.set(n.id,n.id);
  for(const [t,rows] of [...groups.entries()].sort((a,b)=>b[1].length-a[1].length).slice(0,reserve)){const id=`cluster:${t}`;clusters.push({id,type:'cluster',cluster_of:t,label:`${String(t).toUpperCase()} × ${rows.length}`,count:rows.length,aggregated:true,status:'compressed'});for(const n of rows)remap.set(n.id,id)}
  const em=new Map();for(const e of edges){const a=remap.get(e.source),b=remap.get(e.target);if(!a||!b||a===b)continue;const key=JSON.stringify([a,b,e.kind||'']);const cur=em.get(key)||{...e,source:a,target:b,count:0};cur.count+=(Number(e.count)||1);em.set(key,cur)}
  const outEdges=[...em.values()].sort((a,b)=>(b.count||1)-(a.count||1)).slice(0,maxEdges);return{nodes:[...keep,...clusters],edges:outEdges,totalNodes:all.length,hiddenNodes:omitted.length,totalEdges:edges.length,hiddenEdges:Math.max(0,edges.length-outEdges.length)};
}
function anchorFor(type,w,h){const zones={agent:[.50,.12],trajectory:[.55,.20],milestone:[.62,.30],hypothesis:[.73,.23],epistemic:[.80,.31],invariant:[.75,.42],memory:[.80,.67],counterfactual:[.62,.77],runtime:[.78,.58],'runtime-span':[.78,.55],'runtime-log':[.84,.55],'runtime-metric':[.84,.62],service:[.72,.52],database:[.89,.66],'message-bus':[.88,.48],'runtime-route':[.85,.42],'runtime-source':[.67,.63],effect:[.55,.53],dataflow:[.49,.61],file:[.22,.57],symbol:[.38,.48],package:[.20,.27],'build-task':[.31,.22],'ci-workflow':[.18,.15],'ci-job':[.30,.16],'api-spec':[.22,.36],'api-route':[.35,.35],'api-operation':[.43,.36],'db-table':[.28,.72],'db-migration':[.18,.76],'infra-resource':[.18,.43],'container-image':[.12,.30],build:[.14,.24],port:[.12,.38],episode:[.52,.28],evidence:[.62,.42]};let a=zones[type]||[.5,.5];return{x:a[0]*w,y:a[1]*h}}

class WorldGraph{
  constructor(canvas){this.c=canvas;this.x=canvas.getContext('2d');this.nodes=[];this.edges=[];this.hot=new Map();this.heat=new Map();this.tracers=[];this.bursts=[];this.agentTrails=new Map();this.camera={x:0,y:0,z:1,tx:0,ty:0,tz:1};this.focus=null;this.focusUntil=0;this.focusPriority=0;this.lastPhysics=0;this.lod={};this.resize();new ResizeObserver(()=>this.resize()).observe(canvas);requestAnimationFrame(t=>this.frame(t))}
  resize(){const r=this.c.getBoundingClientRect(),d=devicePixelRatio||1;this.c.width=Math.max(1,r.width*d);this.c.height=Math.max(1,r.height*d);this.w=r.width;this.h=r.height;this.x.setTransform(d,0,0,d,0,0);if(!this.camera.x){this.camera.x=this.camera.tx=this.w/2;this.camera.y=this.camera.ty=this.h/2}}
  setData(g){const packed=compressGraph(g);this.lod=packed;const old=new Map(this.nodes.map(n=>[n.id,n]));this.nodes=packed.nodes.map(n=>{let o=old.get(n.id),h=hash(n.id),a=anchorFor(n.cluster_of||n.type,this.w,this.h);return{...n,x:o?.x??a.x+(((h%1000)/1000)-.5)*110,y:o?.y??a.y+((((h>>9)%1000)/1000)-.5)*90,vx:o?.vx||0,vy:o?.vy||0,anchor:a}});const ids=new Set(this.nodes.map(n=>n.id));this.edges=packed.edges.filter(e=>ids.has(e.source)&&ids.has(e.target));this.index();return{visibleNodes:this.nodes.length,totalNodes:packed.totalNodes,hiddenNodes:packed.hiddenNodes,visibleEdges:this.edges.length,totalEdges:packed.totalEdges,hiddenEdges:packed.hiddenEdges}}
  index(){this.byId=new Map();this.byPath=new Map();this.byAgent=new Map();for(let n of this.nodes){this.byId.set(n.id,n);if(n.path&&!this.byPath.has(n.path))this.byPath.set(n.path,n);if(n.agent_id&&!this.byAgent.has(n.agent_id))this.byAgent.set(n.agent_id,n)}}
  find(key){return this.byId.get(key)||this.byPath.get(key)||this.byAgent.get(key)}
  pulse(key){let n=this.find(key);if(n){const now=performance.now();this.hot.set(n.id,now+2800);const h=this.heat.get(n.id)||{score:0,last:now};h.score=Math.min(12,h.score*Math.exp(-(now-h.last)/9000)+1);h.last=now;this.heat.set(n.id,h)}}
  spawnEvent(e){const target=this.find(e.ref_id)||this.find(e.path)||this.find(e.agent_id);const source=this.find(e.agent_id);const color=evtColor(e),now=performance.now(),prio=eventPriority(e);if(target){this.pulse(target.id);if(now>=this.focusUntil||prio>this.focusPriority){this.focus=target.id;this.focusPriority=prio;this.focusUntil=now+(prio>=4?1050:650);this.camera.tx=target.x;this.camera.ty=target.y;this.camera.tz=target.type==='agent'?1.10:1.18}this.bursts.push({x:target.x,y:target.y,t:now,color,status:e.status})}if(source&&target&&source!==target){this.tracers.push({a:source.id,b:target.id,t:now,d:reducedMotion?450:900+Math.random()*550,color,kind:e.category||e.kind});if(e.agent_id){let trail=this.agentTrails.get(e.agent_id)||[];if(!trail.length||trail[trail.length-1].id!==target.id)trail.push({id:target.id,t:now});this.agentTrails.set(e.agent_id,trail.slice(-16))}}if(this.tracers.length>90)this.tracers.splice(0,this.tracers.length-90);if(this.bursts.length>70)this.bursts.splice(0,this.bursts.length-70)}
  frame(t){if(!document.hidden){const dense=this.nodes.length>250;if(!dense||t-this.lastPhysics>32){this.physics();this.lastPhysics=t}this.cameraStep();this.draw(t)}requestAnimationFrame(q=>this.frame(q))}
  cameraStep(){const now=performance.now();if(this.focus&&now>this.focusUntil&&(!this.hot.get(this.focus)||this.hot.get(this.focus)<now)){this.focus=null;this.focusPriority=0;this.camera.tx=this.w/2;this.camera.ty=this.h/2;this.camera.tz=.97}this.camera.x+=(this.camera.tx-this.camera.x)*.035;this.camera.y+=(this.camera.ty-this.camera.y)*.035;this.camera.z+=(this.camera.tz-this.camera.z)*.028}
  physics(){const ns=this.nodes, n=ns.length;if(!n)return;for(let v of ns){let a=anchorFor(v.type,this.w,this.h);v.anchor=a;v.vx+=(a.x-v.x)*.00045;v.vy+=(a.y-v.y)*.00045}
    const map=this.byId;for(let e of this.edges){let a=map.get(e.source),b=map.get(e.target);if(!a||!b)continue;let dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||1,target=58+(hash(e.kind)%55),f=(d-target)*.00011;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}
    for(let i=0;i<n;i++){let a=ns[i];for(let j=i+1;j<n;j++){let b=ns[j],dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+40;if(d2<10000){let f=1.2/d2;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}}a.vx*=.915;a.vy*=.915;a.x=Math.max(24,Math.min(this.w-24,a.x+a.vx));a.y=Math.max(38,Math.min(this.h-24,a.y+a.vy))}}
  transform(){let x=this.x;x.translate(this.w/2,this.h/2);x.scale(this.camera.z,this.camera.z);x.translate(-this.camera.x,-this.camera.y)}
  nodeRadius(n){if(n.type==='cluster')return Math.min(11,5+Math.log2(1+Number(n.count||1)));return n.type==='agent'?8:n.type==='counterfactual'?6.5:n.type==='hypothesis'?5.5:n.type==='service'||n.type==='database'?5:n.type==='effect'?3.4:3.1}
  draw(t){let x=this.x;x.clearRect(0,0,this.w,this.h);x.save();this.transform();const map=this.byId;
    // faint topology rings make the graph feel spatial without behaving like a terminal/dashboard.
    x.lineWidth=.5;for(let r of [85,170,255]){x.beginPath();x.arc(this.w*.5,this.h*.5,r,0,Math.PI*2);x.strokeStyle='rgba(61,117,190,.035)';x.stroke()}
    for(let e of this.edges){let a=map.get(e.source),b=map.get(e.target);if(!a||!b)continue;let col=Number(e.error_count||0)>0?'#ff4e68':edgeColor(e.kind),hot=(this.hot.get(a.id)||0)>t||(this.hot.get(b.id)||0)>t;x.lineWidth=hot?1.05:.55;x.strokeStyle=col+(hot?'60':'20');x.beginPath();let mx=(a.x+b.x)/2+(a.y-b.y)*.04,my=(a.y+b.y)/2+(b.x-a.x)*.04;x.moveTo(a.x,a.y);x.quadraticCurveTo(mx,my,b.x,b.y);x.stroke();if(/runtime|span|effect|dataflow|call|depends|db-|message/.test(e.kind)){const pc=Math.min(3,1+Math.floor(Math.log2(Math.max(1,Number(e.count||1)))));for(let pi=0;pi<pc;pi++){let phase=((t/(1500-Math.min(500,Number(e.count||1)*12)))+(hash(e.source+e.target)%100)/100+pi/pc)%1,px=(1-phase)*(1-phase)*a.x+2*(1-phase)*phase*mx+phase*phase*b.x,py=(1-phase)*(1-phase)*a.y+2*(1-phase)*phase*my+phase*phase*b.y;x.fillStyle=col;x.globalAlpha=.48;x.shadowBlur=9;x.shadowColor=col;x.beginPath();x.arc(px,py,Number(e.error_count||0)>0?1.5:1.1,0,Math.PI*2);x.fill()}x.globalAlpha=1;x.shadowBlur=0}}
    for(const [aid,trail0] of this.agentTrails){const trail=trail0.filter(q=>t-q.t<18000);this.agentTrails.set(aid,trail);if(trail.length<2)continue;const col=colorForAgent(aid);x.strokeStyle=col+'35';x.lineWidth=1;x.beginPath();let started=false;for(const q of trail){const n=map.get(q.id);if(!n)continue;if(!started){x.moveTo(n.x,n.y);started=true}else x.lineTo(n.x,n.y)}if(started)x.stroke()}
    for(let tr of this.tracers){let a=map.get(tr.a),b=map.get(tr.b);if(!a||!b)continue;let p=(t-tr.t)/tr.d;if(p<0||p>1)continue;let mx=(a.x+b.x)/2+(a.y-b.y)*.12,my=(a.y+b.y)/2+(b.x-a.x)*.12;for(let k=0;k<7;k++){let q=Math.max(0,p-k*.025),px=(1-q)*(1-q)*a.x+2*(1-q)*q*mx+q*q*b.x,py=(1-q)*(1-q)*a.y+2*(1-q)*q*my+q*q*b.y;x.globalAlpha=(1-k/7)*(.95-p*.2);x.fillStyle=tr.color;x.shadowBlur=14-k;x.shadowColor=tr.color;x.beginPath();x.arc(px,py,2-k*.18,0,Math.PI*2);x.fill()}x.globalAlpha=1;x.shadowBlur=0}
    this.tracers=this.tracers.filter(q=>t-q.t<q.d+150);
    for(let b of this.bursts){let p=(t-b.t)/1150;if(p<0||p>1)continue;x.globalAlpha=1-p;x.strokeStyle=b.color;x.lineWidth=1.3;x.beginPath();x.arc(b.x,b.y,6+p*30,0,Math.PI*2);x.stroke();if(String(b.status||'').match(/fail|error/i)){x.strokeStyle='#ff4e68';x.beginPath();x.arc(b.x,b.y,10+p*42,0,Math.PI*2);x.stroke()}}x.globalAlpha=1;this.bursts=this.bursts.filter(q=>t-q.t<1300);
    for(let n of this.nodes){let col=n.type==='cluster'?(typeColors[n.cluster_of]||'#60789b'):nodeColor(n),hot=(this.hot.get(n.id)||0)>t,r=this.nodeRadius(n);const hs=this.heat.get(n.id);let hv=0;if(hs){hv=hs.score*Math.exp(-(t-hs.last)/12000);if(hv<.03)this.heat.delete(n.id)}r+=Math.min(2.8,hv*.22);if(hot){let phase=(t%850)/850;x.beginPath();x.arc(n.x,n.y,r+4+phase*13,0,Math.PI*2);x.strokeStyle=col+(Math.floor((1-phase)*170).toString(16).padStart(2,'0'));x.lineWidth=1.1;x.stroke()}if(n.type==='agent'){x.strokeStyle=col+'80';x.lineWidth=.8;x.beginPath();x.arc(n.x,n.y,r+5+Math.sin(t/700)*1.2,0,Math.PI*2);x.stroke()}x.shadowBlur=hot?22:(n.type==='agent'?15:7);x.shadowColor=col;x.fillStyle=col;x.beginPath();if(n.type==='counterfactual'){for(let i=0;i<6;i++){let a=Math.PI/3*i+(Math.PI/6);let px=n.x+Math.cos(a)*r,py=n.y+Math.sin(a)*r;i?x.lineTo(px,py):x.moveTo(px,py)}x.closePath()}else{x.arc(n.x,n.y,r,0,Math.PI*2)}x.fill();x.shadowBlur=0;if(n.type==='agent'||n.type==='hypothesis'||n.type==='service'||n.type==='database'||n.type==='cluster'||hot){x.fillStyle=hot?'#f0fbff':'#7588a7';x.font='7px ui-monospace,monospace';x.fillText(short(n.label||'',30),n.x+r+4,n.y+2)}}
    x.restore();
  }
}
const graph=new WorldGraph($('#worldMap'));

(function ambient(){const c=$('#ambient'),x=c.getContext('2d');let stars=Array.from({length:110},(_,i)=>({x:Math.random(),y:Math.random(),r:Math.random()*1.3+.2,v:(Math.random()*.00007+.000015),c:palette[i%palette.length],a:Math.random()*.25+.08}));let drops=Array.from({length:22},(_,i)=>({x:Math.random(),y:Math.random(),v:.0003+Math.random()*.0007,len:20+Math.random()*80,c:palette[(i+3)%palette.length]}));function rs(){let d=devicePixelRatio||1;c.width=innerWidth*d;c.height=innerHeight*d;x.setTransform(d,0,0,d,0,0)}addEventListener('resize',rs);rs();function f(t){if(document.hidden){requestAnimationFrame(f);return}x.clearRect(0,0,innerWidth,innerHeight);for(let p of stars){p.y-=p.v;if(p.y<0)p.y=1;x.globalAlpha=p.a*(.75+.25*Math.sin(t/1000+p.x*15));x.fillStyle=p.c;x.fillRect(p.x*innerWidth,p.y*innerHeight,p.r,p.r)}for(let d of drops){d.y+=d.v*(reducedMotion?.25:1);if(d.y>1.1)d.y=-.1;let gx=x.createLinearGradient(0,(d.y*innerHeight)-d.len,0,d.y*innerHeight);gx.addColorStop(0,'transparent');gx.addColorStop(1,d.c+'40');x.globalAlpha=.32;x.strokeStyle=gx;x.beginPath();x.moveTo(d.x*innerWidth,(d.y*innerHeight)-d.len);x.lineTo(d.x*innerWidth,d.y*innerHeight);x.stroke()}x.globalAlpha=1;requestAnimationFrame(f)}requestAnimationFrame(f)})();

setStageMode('world');setInterval(()=>{$('#clock').textContent=new Date().toLocaleTimeString();updateRate()},500);setInterval(snapshot,2600);snapshot().then(connect);
