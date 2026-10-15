/* RydeResolve front-end. English by default, EN | 中文 toggle (choice remembered in this browser). */
const I18N = {
  en: {
    tagline:'Multi-agent autonomous dispute resolution · Tencent Cloud AI CAN DO IT 2026',
    loading:'Loading…', backendTitle:'Choose the backend that drives the agents',
    beDefault:'Default backend', beLlm:'Real LLM', beDet:'Deterministic fallback',
    presetTitle:'Preset tickets, one-click replay', replay:'Replay', replaying:'Replaying…',
    fileHead:'File a new dispute', fileHint:'Write it in your own words; the system works out the dispute type',
    placeholder:'e.g. The driver went round and round and the fare was way higher than the estimate',
    tryHint:'Try:', chipEn:'English', chipSl:'Singlish', chipMs:'Malay', chipTa:'Tamil', chipZh:'Chinese',
    tripLbl:'Trip', submit:'Submit and rule', ruling_btn:'Ruling…',
    fileFoot:"Evidence can only come from a real trip: GPS, chat and app events are pulled by the platform, you don't supply them.",
    a_intake:'Intake agent', a_rider:'Rider advocate', a_driver:'Driver advocate', a_judge:'Judge', a_safety:'Safety net',
    idle:'Idle', working:'Gathering…', finished:'Done', reasoning:'Reasoning',
    emptyHint:'Write a complaint in your own words above, pick a trip and press "Submit and rule".<br>The system first works out the dispute type, then two advocate agents gather evidence in parallel and a judge verifies it independently before ruling.<br><span style="font-size:12px">(The dropdown at the top right replays the preset tickets.)</span>',
    badgeLlm:(p,m)=>`${p} · ${m}`, badgeDet:'Deterministic fallback · no API key', badgeFail:'Health check failed',
    t_route:'Route', t_noshow:'No-show', t_fare:'Fare', t_property:'Property', t_safety:'Safety', t_routeFull:'Route deviation', t_noshowFull:'No-show charge',
    chipFare:'Fare', chipProp:'Cleaning fee', chipSafe:'Safety', a_safetycase:'Safety case file',
    ppHead:'Policy v2.1 path', ppPath:{ai_final:'AI final ruling',ai_ruling_if_confident:'AI ruling if confident',human_review:'Human review'}, ppReq:'Required confidence', ppFraud:'Fraud flag raises the bar to 95%', ppClauses:'Clauses', ppBreak:'Confidence breakdown',
    cbk:{evidence_completeness:'Evidence completeness',policy_clarity:'Policy clarity',precedent_alignment:'Precedent alignment',party_credibility:'Party credibility'},
    goodwill:'Goodwill credit', pendApproval:' · AI recommendation, human approval required', recHead:'AI recommendation (not executed)',
    sfHead:'Safety case file for the human reviewer', sfInterim:'Suggested interim measures (policy 5.3)', sfNote:'The AI has not determined fault or recommended a resolution.',
    argsResult:'Arguments / result', ok:'✓ done', fail:'✗ failed', pending:'…',
    noCase:'No case', riderCase:'Rider case', driverCase:'Driver case', claim:'Claim', ask:'Request', clauses:'Clauses cited',
    cbHead:"Rider's own words", cbTrip:'Trip', cbFoot:'No dispute type selected: the intake agent decides it',
    tgHead:'Intake result', tgConf:'Classification confidence', tgClaim:'Normalized claim', tgClaimed:'claimed',
    tgSigs:'Signals matched', tgFoot:id=>`Ticket ${id} filed, moving to the advocates`,
    snHead:'Safety net check (deterministic rules, independent of the model)', snPoints:'Distinct evidence points',
    snCount:(c,t)=>`${c} / minimum ${t}`, snEmpty:'empty or near-empty ✗', snOk:'enough ✓', snShort:'too few ✗', snMet:'met ✓',
    snTrig:'Override triggered → forced escalation to a human', snPass:"Not triggered, the model's ruling stands",
    snFlag:"Safety net override: evidence base too thin, forced escalation (the model's confidence does not count)",
    refund:'Refund', conf:'Confidence', escalated:' · escalated to a human', evTitle:'Evidence cited in verification',
    maHead:ov=>`Model's independent assessment (judge agent's raw output${ov?', overridden by the safety net':''})`,
    maRuling:'Ruling', maRefund:'Refund',
    rl:{upheld:'Upheld (refund)', rejected:'Rejected', partial:'Partially upheld', escalated:'Escalated to human'},
    rateLimit:'Real LLM quota / rate limit (429). Switch the backend at the top right to "Deterministic fallback" and run again: same flow, same tools, same rulings, only the reasoning steps are scripted.\n\n',
  },
  zh: {
    tagline:'多智能体自主争议裁决 · 腾讯云 AI CAN DO IT 2026',
    loading:'载入中…', backendTitle:'选择驱动智能体的后端',
    beDefault:'默认后端', beLlm:'真实 LLM', beDet:'确定性回退',
    presetTitle:'预置工单，一键重放', replay:'重放', replaying:'重放中…',
    fileHead:'提交新争议', fileHint:'用你自己的话写，系统自己判定争议类型',
    placeholder:'例：司机绕了一大圈才到，明明半小时的路走了一个多小时，还多收我钱',
    tryHint:'试试：', chipEn:'英文', chipSl:'新加坡式英语', chipMs:'马来语', chipTa:'泰米尔语', chipZh:'中文',
    tripLbl:'关联行程', submit:'提交并裁决', ruling_btn:'裁决中…',
    fileFoot:'证据只能来自真实发生过的行程：GPS、聊天、App 事件都由平台调取，不需要你提供。',
    a_intake:'受理分类智能体', a_rider:'乘客辩护智能体', a_driver:'司机辩护智能体', a_judge:'法官智能体', a_safety:'安全网校验',
    idle:'待命', working:'取证中…', finished:'已完成', reasoning:'推理',
    emptyHint:'在上方用你自己的话写一条投诉，选好行程，点「提交并裁决」。<br>系统会先判定争议类型，再由两位辩护智能体并行取证、法官独立核验给出裁决。<br><span style="font-size:12px">（右上角下拉可重放预置工单）</span>',
    badgeLlm:(p,m)=>`${p} · ${m}`, badgeDet:'确定性回退 · 无需 API key', badgeFail:'健康检查失败',
    t_route:'绕路', t_noshow:'爽约', t_fare:'车费', t_property:'财物', t_safety:'安全', t_routeFull:'绕路多收费', t_noshowFull:'爽约取消费',
    chipFare:'车费争议', chipProp:'清洁费', chipSafe:'安全事件', a_safetycase:'安全案件材料',
    ppHead:'政策 v2.1 裁决路径', ppPath:{ai_final:'AI 终局裁决',ai_ruling_if_confident:'置信度足够时 AI 裁决',human_review:'人工复核'}, ppReq:'所需置信度', ppFraud:'欺诈标记将门槛提高到 95%', ppClauses:'条款', ppBreak:'置信度构成',
    cbk:{evidence_completeness:'证据完整度',policy_clarity:'政策清晰度',precedent_alignment:'先例一致度',party_credibility:'当事人可信度'},
    goodwill:'善意补偿', pendApproval:' · AI 建议，需人工批准', recHead:'AI 建议（未执行）',
    sfHead:'供人工复核的安全案件材料', sfInterim:'建议的临时措施（政策 5.3）', sfNote:'AI 未判定责任，也未建议处理方案。',
    argsResult:'参数 / 结果', ok:'✓ 完成', fail:'✗ 失败', pending:'…',
    noCase:'无案件', riderCase:'乘客方案件', driverCase:'司机方案件', claim:'主张', ask:'诉求', clauses:'引用条款',
    cbHead:'乘客原话', cbTrip:'行程', cbFoot:'未选择争议类型 —— 类型由受理分类智能体判定',
    tgHead:'受理分类结果', tgConf:'分类置信度', tgClaim:'归一化主张', tgClaimed:'主张',
    tgSigs:'命中信号', tgFoot:id=>`工单 ${id} 已建档，进入辩护阶段`,
    snHead:'安全网校验（确定性规则，与模型无关）', snPoints:'独立数据点',
    snCount:(c,t)=>`${c} 条 / 下限 ${t}`, snEmpty:'空或近空 ✗', snOk:'充足 ✓', snShort:'不足 ✗', snMet:'达标 ✓',
    snTrig:'触发覆盖 → 强制升级人工', snPass:'未触发，维持模型裁决',
    snFlag:'安全网覆盖：证据基础不足，强制升级人工（模型置信度不作数）',
    refund:'退费', conf:'置信度', escalated:' · 已升级人工', evTitle:'核验引用的证据',
    maHead:ov=>`模型独立判断（法官智能体原始输出${ov?'，已被安全网覆盖':''}）`,
    maRuling:'裁决', maRefund:'退款',
    rl:{upheld:'支持（退费）', rejected:'驳回', partial:'部分支持', escalated:'升级人工'},
    rateLimit:'真实 LLM 额度/限流（429）。请把右上角后端切换为「确定性回退」再跑一次 —— 流程、工具与裁决结果完全一致，只是推理步骤由剧本驱动。\n\n',
  },
};
const CUR = 'S$';

let LANG = 'en';
try { const s = localStorage.getItem('rr_lang'); if (s === 'zh' || s === 'en') LANG = s; } catch (e) {}
const T = k => (I18N[LANG][k] !== undefined ? I18N[LANG][k] : I18N.en[k]);
const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

const AGENTS = {
  intake:{key:'a_intake',cls:'intake'}, rider_advocate:{key:'a_rider',cls:'rider'},
  driver_advocate:{key:'a_driver',cls:'driver'}, judge:{key:'a_judge',cls:'judge'}, safety_net:{key:'a_safety',cls:'safety'},
  safety_case:{key:'a_safetycase',cls:'safety'},
};
const agentName = a => AGENTS[a] ? T(AGENTS[a].key) : a;

const el = id => document.getElementById(id);
const timeline = el('timeline'), runBtn = el('runBtn'), fileBtn = el('fileBtn');
const sel = el('disputeSelect'), tripSel = el('tripSelect');
const complaintInput = el('complaintInput'), modeBadge = el('modeBadge');

let lastToolEl = {};
let health = null, disputes = [], trips = [];
let busy = null;   // 'file' | 'run' | null

function typeLabel(t){ return ({route_deviation:'t_route',no_show_charge:'t_noshow',fare_dispute:'t_fare',property_damage:'t_property',safety_incident:'t_safety'}[t]) ? T({route_deviation:'t_route',no_show_charge:'t_noshow',fare_dispute:'t_fare',property_damage:'t_property',safety_incident:'t_safety'}[t]) : t; }
function rulingLabel(r){ return (T('rl')||{})[r] || r; }

function applyStatic(){
  document.documentElement.lang = LANG === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach(n => { n.textContent = T(n.dataset.i18n); });
  document.querySelectorAll('[data-i18n-html]').forEach(n => { n.innerHTML = T(n.dataset.i18nHtml); });
  document.querySelectorAll('[data-i18n-title]').forEach(n => { n.title = T(n.dataset.i18nTitle); });
  document.querySelectorAll('[data-i18n-ph]').forEach(n => { n.placeholder = T(n.dataset.i18nPh); });
  document.querySelectorAll('#langToggle button').forEach(b => b.classList.toggle('on', b.dataset.lang === LANG));
  document.title = LANG === 'zh' ? 'RydeResolve | 多智能体争议裁决' : 'RydeResolve | Multi-agent dispute resolution';
  renderBadge(); renderDropdowns();
  if (busy !== 'file') fileBtn.textContent = T('submit');
  if (busy !== 'run') runBtn.textContent = T('replay');
}

function renderBadge(){
  if (!health) return;
  const llm = health.llm_mode === 'llm';
  modeBadge.textContent = llm ? T('badgeLlm')(health.llm_provider || 'LLM', health.model || health.hunyuan_model) : T('badgeDet');
  modeBadge.className = 'mode-badge ' + (llm ? 'llm' : 'det');
}

function renderDropdowns(){
  const cur = sel.value, curT = tripSel.value;
  sel.innerHTML = ''; tripSel.innerHTML = '';
  disputes.forEach(x => {
    const o = document.createElement('option'); o.value = x.dispute_id;
    o.textContent = `${x.dispute_id} · ${typeLabel(x.dispute_type)} · ${x.description.slice(0,28)}…`;
    sel.appendChild(o);
  });
  trips.forEach(x => {
    const o = document.createElement('option'); o.value = x.trip_id;
    o.textContent = `${x.trip_id} · ${x.route}${x.outcome ? ' · ' + x.outcome : ''}`;
    tripSel.appendChild(o);
  });
  if (cur) sel.value = cur; if (curT) tripSel.value = curT;
}

async function boot(){
  applyStatic();
  try { health = await fetch('/api/health').then(r => r.json()); renderBadge(); }
  catch (e) { modeBadge.textContent = T('badgeFail'); }
  try {
    disputes = (await fetch('/api/disputes').then(r => r.json())).disputes || [];
    trips = (await fetch('/api/trips').then(r => r.json())).trips || [];
  } catch (e) {}
  renderDropdowns();
  sel.disabled = false; runBtn.disabled = false; tripSel.disabled = false; fileBtn.disabled = false;
}

document.querySelectorAll('#langToggle button').forEach(b => b.addEventListener('click', () => {
  LANG = b.dataset.lang;
  try { localStorage.setItem('rr_lang', LANG); } catch (e) {}
  applyStatic();
  // Results already on screen stay in the language they were produced in; re-run to see them in the new one.
}));

document.querySelectorAll('.chip').forEach(c => c.addEventListener('click', () => {
  complaintInput.value = c.dataset.text; complaintInput.focus();
}));

function resetUI(){
  timeline.innerHTML = ''; lastToolEl = {};
  document.querySelectorAll('.agent-card').forEach(c => { c.classList.remove('active','done'); c.querySelector('.ac-status').textContent = T('idle'); });
}
function setAgentStatus(agent, status){
  const card = document.querySelector(`.agent-card[data-agent="${agent}"]`); if (!card) return;
  const st = card.querySelector('.ac-status');
  if (status === 'active'){ card.classList.add('active'); card.classList.remove('done'); st.textContent = T('working'); }
  else if (status === 'done'){ card.classList.remove('active'); card.classList.add('done'); st.textContent = T('finished'); }
}

function scroll(){ window.scrollTo({top:document.body.scrollHeight, behavior:'smooth'}); }
function addPhase(msg){
  const w = document.createElement('div'); w.className = 'phase';
  w.innerHTML = `<span class="ttl">${esc(msg)}</span><span class="bar"></span>`; timeline.appendChild(w);
}
function addThinking(agent, content){
  const cls = (AGENTS[agent]||{}).cls || '';
  const t = document.getElementById('tpl-thinking').content.cloneNode(true);
  if (cls) t.querySelector('.thinking').classList.add(cls);
  t.querySelector('.who').textContent = agentName(agent);
  t.querySelector('.lbl').textContent = T('reasoning');
  t.querySelector('.msg-body').textContent = content; timeline.appendChild(t); scroll();
}
function addToolCall(agent, tool, args, summary){
  const w = document.createElement('div'); w.className = 'tool';
  w.innerHTML = `
    <div class="tc-head"><span class="fn">${esc(tool)}(</span><span class="arr">${esc((summary||'').replace(/^[^(]*\((.*)\)/,'$1'))}</span><span class="fn">)</span>
      <span class="tc-status">${T('pending')}</span></div>
    <details><summary>${T('argsResult')}</summary><pre>${esc(JSON.stringify(args,null,2))}</pre></details>`;
  timeline.appendChild(w); lastToolEl[agent] = w; scroll();
}
function addToolResult(agent, tool, ok, result){
  const w = lastToolEl[agent]; if (!w) return;
  const st = w.querySelector('.tc-status');
  st.textContent = ok ? T('ok') : T('fail'); st.className = 'tc-status ' + (ok ? 'ok' : 'err');
  w.querySelector('pre').textContent = JSON.stringify(result, null, 2); scroll();
}
function caseCard(cls, c){
  const d = document.createElement('div'); d.className = 'case ' + cls;
  if (!c){ d.innerHTML = `<h4>${T('noCase')}</h4>`; return d; }
  const ev = (c.evidence_cited||[]).map(e => `<div class="ev">${esc(e)}</div>`).join('');
  d.innerHTML = `<h4>${cls==='rider'?T('riderCase'):T('driverCase')}</h4>
    <div class="claim"><b>${T('claim')}:</b> ${esc(c.claim)}</div>
    <div class="claim"><b>${T('ask')}:</b> ${esc(c.requested_outcome)}${c.requested_amount!=null?` · ${CUR}${esc(c.requested_amount)}`:''}</div>
    <div class="ev-title" style="color:var(--mut);font-size:11px;margin-top:6px">${T('clauses')}: ${esc((c.policy_clauses_referenced||[]).join(', ')||'-')}</div>${ev}`;
  return d;
}
function addCases(rider, driver){
  const w = document.createElement('div'); w.className = 'cases';
  w.appendChild(caseCard('rider', rider)); w.appendChild(caseCard('driver', driver));
  timeline.appendChild(w); scroll();
}
function addComplaint(text, tripId){
  const d = document.createElement('div'); d.className = 'complaint-box';
  d.innerHTML = `<div class="cb-head">${T('cbHead')}<span class="cb-trip">${T('cbTrip')} ${esc(tripId)}</span></div>
    <div class="cb-body">${esc(text)}</div><div class="cb-foot">${T('cbFoot')}</div>`;
  timeline.appendChild(d); scroll();
}
function addTriage(t){
  const d = document.createElement('div'); d.className = 'triage-box';
  const sigs = (t.detected_signals||[]).map(s => `<span class="tg-sig">${esc(s)}</span>`).join('');
  d.innerHTML = `
    <div class="tg-head">${T('tgHead')}</div>
    <div class="tg-line"><span class="tg-badge">${esc(t.dispute_type_label || typeLabel(t.dispute_type))}</span>
      <span class="tg-type">${esc(t.dispute_type)}</span>
      <span class="tg-conf">${T('tgConf')} <b>${esc(t.classification_confidence)}</b></span></div>
    <div class="tg-claim"><b>${T('tgClaim')}:</b> ${esc(t.normalized_claim)}${t.requested_amount!=null?` · ${T('tgClaimed')} ${CUR}${esc(t.requested_amount)}`:''}</div>
    <div class="tg-reason">${esc(t.classification_reasoning)}</div>
    ${sigs?`<div class="tg-sigs">${T('tgSigs')}: ${sigs}</div>`:''}
    <div class="tg-foot">${T('tgFoot')(esc(t.dispute_id||'-'))}</div>`;
  timeline.appendChild(d); scroll();
}
function addSafetyNet(sn){
  const card = document.createElement('div'); card.className = 'safety-box' + (sn.triggered?' triggered':' passed');
  const chk = sn.checks||{}, src = chk.evidence_sources||{};
  const rows = Object.keys(src).map(k => { const i = src[k];
    return `<div class="sn-row"><span class="sn-k">${esc(k)}</span><span class="sn-v">${T('snCount')(i.count,i.threshold)}</span>
      <span class="sn-f ${i.near_empty?'bad':'good'}">${i.near_empty?T('snEmpty'):T('snOk')}</span></div>`; }).join('');
  const reasons = (sn.reasons||[]).map(x => `<div class="sn-reason">✗ ${esc(x)}</div>`).join('');
  const short = chk.distinct_evidence_points < chk.min_evidence_points;
  card.innerHTML = `<div class="sn-head">${T('snHead')}</div>
    <div class="sn-row"><span class="sn-k">${T('snPoints')}</span>
      <span class="sn-v">${T('snCount')(chk.distinct_evidence_points, chk.min_evidence_points)}</span>
      <span class="sn-f ${short?'bad':'good'}">${short?T('snShort'):T('snMet')}</span></div>
    ${rows}${reasons}<div class="sn-verdict">${sn.triggered?T('snTrig'):T('snPass')}</div>`;
  timeline.appendChild(card); scroll();
}
function addRuling(r){
  const card = document.createElement('div'); const ma = r.model_assessment||null, sn = r.safety_net||null;
  card.className = 'ruling' + (r.ruling==='escalated'?' escalated':'');
  const cls = {upheld:'upheld',rejected:'rejected',partial:'partial',escalated:'escalated'}[r.ruling]||'partial';
  const ev = (r.evidence_cited||[]).map(e => `<div class="r-ev">${esc(e)}</div>`).join('');
  const refund = r.refund_amount!=null ? `<div class="refund">${T('refund')} <b>${CUR}${esc(r.refund_amount)}</b></div>` : '';
  const gw = r.goodwill_credit ? `<div class="refund">${T('goodwill')} <b>${CUR}${esc(r.goodwill_credit)}</b></div>` : '';
  const pp = r.policy_path;
  let ppBox = '';
  if (pp){
    const bk = r.confidence_breakdown ? Object.keys(r.confidence_breakdown).map(k => `<span class="tg-sig">${esc((T('cbk')||{})[k]||k)} ${esc(r.confidence_breakdown[k])}</span>`).join('') : '';
    ppBox = `<div class="triage-box"><div class="tg-head">${T('ppHead')}</div>
      <div class="tg-line"><span class="tg-badge">${esc((T('ppPath')||{})[pp.path]||pp.path)}</span>
      <span class="tg-conf">${T('ppClauses')}: ${esc((r.policy_clauses||[]).join(', ')||pp.clause)}</span>
      ${pp.required_confidence!=null?`<span class="tg-conf">${T('ppReq')} <b>${esc(pp.required_confidence)}</b></span>`:''}</div>
      ${pp.fraud_flag?`<div class="tg-reason">${T('ppFraud')}</div>`:''}
      ${(pp.reasons||[]).map(x=>`<div class="tg-reason">${esc(x)}</div>`).join('')}
      ${bk?`<div class="tg-sigs">${T('ppBreak')}: ${bk}</div>`:''}</div>`;
  }
  const rec = r.recommendation ? `<div class="ma-box"><div class="ma-head">${T('recHead')}</div><div class="ma-line"><b>${T('maRuling')}</b> ${esc(rulingLabel(r.recommendation.ruling))}　<b>${T('maRefund')}</b> ${r.recommendation.refund_amount!=null?CUR+esc(r.recommendation.refund_amount):'-'}</div></div>` : '';
  let sfBox = '';
  if (r.case_file){
    sfBox = `<div class="ma-box"><div class="ma-head">${T('sfHead')}</div>${(r.case_file.facts||[]).map(x=>`<div class="r-ev">${esc(x)}</div>`).join('')}
      <div class="ma-head" style="margin-top:8px">${T('sfInterim')}</div>${(r.case_file.interim_measures||[]).map(x=>`<div class="r-ev">${esc(x)}</div>`).join('')}
      <div class="ma-reason">${T('sfNote')}</div></div>`;
  }
  const esc_ = (r.escalation_required && r.escalation_summary) ? `<div class="esc-box">${esc(r.escalation_summary)}</div>` : '';
  let maBox = '';
  if (ma){
    const maEv = (ma.evidence_cited||[]).map(e => `<div class="r-ev">${esc(e)}</div>`).join('');
    maBox = `<div class="ma-box"><div class="ma-head">${T('maHead')(sn&&sn.triggered)}</div>
      <div class="ma-line"><b>${T('maRuling')}</b> ${esc(rulingLabel(ma.ruling))}　<b>${T('maRefund')}</b> ${ma.refund_amount!=null?CUR+esc(ma.refund_amount):'-'}　<b>${T('conf')}</b> ${esc(ma.confidence_score)}</div>
      <div class="ma-reason">${esc(ma.reasoning)}</div>${maEv}</div>`;
  }
  card.innerHTML = `<div class="r-head"><span class="badge ${cls}">${esc(rulingLabel(r.ruling))}</span>
      <span class="conf">${T('conf')} <b>${esc(r.confidence_score)}</b>${r.ruling==='escalated'?T('escalated'):(r.escalation_required?T('pendApproval'):'')}</span>${refund}${gw}</div>
    ${sn&&sn.triggered?`<div class="sn-flag">${T('snFlag')}</div>`:''}
    <div class="r-reason">${esc(r.reasoning)}</div><div class="r-ev-title">${T('evTitle')}</div>${ev}${ppBox}${rec}${sfBox}${maBox}${esc_}`;
  timeline.appendChild(card); scroll();
}

function appendEvent(ev){
  ev.agent = ev.agent || ev.role;   // safety-net events carry `role` only
  switch (ev.type){
    case 'phase':
      addPhase(ev.message);
      if (ev.phase==='intake') setAgentStatus('intake','active');
      else if (ev.phase==='advocates'){ setAgentStatus('rider_advocate','active'); setAgentStatus('driver_advocate','active'); }
      else if (ev.phase==='cases_submitted'){ setAgentStatus('rider_advocate','done'); setAgentStatus('driver_advocate','done'); addCases(ev.rider_case, ev.driver_case); }
      else if (ev.phase==='judge') setAgentStatus('judge','active');
      else if (ev.phase==='safety_net') setAgentStatus('safety_net','active');
      else if (ev.phase==='safety_intake') setAgentStatus('safety_net','active');
      break;
    case 'complaint_received': addComplaint(ev.complaint, ev.trip_id); break;
    case 'triage_result': setAgentStatus('intake','done'); addTriage(ev); break;
    case 'thinking': addThinking(ev.agent, ev.content); break;
    case 'tool_call': addToolCall(ev.agent, ev.tool, ev.args, ev.summary); break;
    case 'tool_result': addToolResult(ev.agent, ev.tool, ev.ok, ev.result); break;
    case 'safety_net': setAgentStatus('safety_net','done'); addSafetyNet(ev); break;
    case 'ruling': setAgentStatus('judge','done'); setAgentStatus('safety_net','done'); addRuling(ev.ruling); break;
    case 'warning': addThinking(ev.agent, ev.content); break;
    case 'done': break;
    case 'error': {
      const d = document.createElement('div'); d.className = 'err';
      let msg = ev.message + '\n' + (ev.trace||'');
      if (/429|quota|rate|RESOURCE_EXHAUSTED/i.test(msg)) msg = T('rateLimit') + msg;
      d.textContent = msg; timeline.appendChild(d); scroll(); } break;
  }
}

function extraQuery(){
  const be = (document.getElementById('backendSelect')||{}).value || '';
  return (be ? `&mode=${encodeURIComponent(be)}` : '') + `&lang=${LANG}`;
}
function openStream(url, btn, busyText, kind){
  btn.disabled = true; btn.textContent = busyText; busy = kind; resetUI();
  const es = new EventSource(url);
  const restore = () => { busy = null; btn.disabled = false; btn.textContent = btn===fileBtn ? T('submit') : T('replay'); };
  es.onmessage = e => { const ev = JSON.parse(e.data); if (ev.type==='done'){ es.close(); restore(); return; } appendEvent(ev); };
  es.onerror = () => { es.close(); restore(); };
  const watcher = setInterval(() => { if (es.readyState===2){ clearInterval(watcher); restore(); } }, 400);
}
function runFreeform(){
  const text = (complaintInput.value||'').trim(), tripId = tripSel.value;
  if (!text){ complaintInput.focus(); return; } if (!tripId) return;
  openStream(`/api/file/stream?trip_id=${encodeURIComponent(tripId)}&complaint=${encodeURIComponent(text)}${extraQuery()}`, fileBtn, T('ruling_btn'), 'file');
}
function runPreset(){
  const id = sel.value; if (!id) return;
  openStream(`/api/resolve/${id}/stream?${extraQuery().replace(/^&/,'')}`, runBtn, T('replaying'), 'run');
}
fileBtn.addEventListener('click', runFreeform);
runBtn.addEventListener('click', runPreset);
complaintInput.addEventListener('keydown', e => { if ((e.metaKey||e.ctrlKey) && e.key==='Enter') runFreeform(); });
boot();
