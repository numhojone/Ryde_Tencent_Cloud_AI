/* RydeResolve front-end — the dispute plays out as a group chat between the agents.
   English by default, EN | 中文 toggle (choice remembered in this browser).
   The SSE event stream and the API are consumed exactly as the backend emits them. */

const I18N = {
  en: {
    tagline:'Multi-agent autonomous dispute resolution · Tencent Cloud AI CAN DO IT 2026',
    loading:'Loading…', backendTitle:'Choose the backend that drives the agents',
    beLlm:'Live AI', beDet:'Offline demo', offlineDemoTag:'Offline demo (scripted agents)',
    presetTitle:'Preset tickets, one-click replay', replay:'Replay', replaying:'Replaying…',
    fileHint:'Write it in your own words; the system works out the dispute type',
    placeholder:'Describe what went wrong, in your own words…',
    tryHint:'Try:', chipEn:'English', chipSl:'Singlish', chipMs:'Malay', chipTa:'Tamil', chipZh:'Chinese',
    tripLbl:'Trip', submit:'Submit and rule', ruling_btn:'Ruling…',
    fileFoot:"Your story picks the category and the trip; the platform's own records (GPS, chat, fares, app events) decide the ruling.",
    a_intake:'Intake agent', a_rider:'Rider advocate', a_driver:'Driver advocate', a_judge:'Judge', a_safety:'Safety net',
    p_rider:'Rider', p_system:'Policy engine',
    idle:'Idle', working:'Gathering…', finished:'Done', reasoning:'Reasoning',
    emptyHint:'<strong>A dispute is settled here as a group chat.</strong><br>'
      + 'Write the complaint in your own words below and press “Submit and rule”. The trip is matched from your story, or you can pick it.<br>'
      + 'The intake agent classifies it, a rider advocate and a driver advocate gather evidence and argue in parallel, '
      + 'then a judge verifies the evidence independently and rules.'
      + '<span class="es-note">The dropdown in the header replays the preset tickets.</span>',
    badgeLlm:(p,m)=>`${p} · ${m}`, badgeDet:'Deterministic fallback · no API key', badgeFail:'Health check failed',
    t_route:'Route', t_noshow:'No-show', t_fare:'Fare', t_property:'Property', t_safety:'Safety', t_routeFull:'Route deviation', t_noshowFull:'No-show charge',
    chipFare:'Fare', chipProp:'Cleaning fee', chipSafe:'Safety', a_safetycase:'Safety case file',
    ppHead:'Policy v2.1 path', ppPath:{ai_final:'AI final ruling',ai_ruling_if_confident:'AI ruling if confident',human_review:'Human review'},
    ppReq:'Required confidence', ppFraud:'Fraud flag raises the bar to 95%', ppClauses:'Clauses', ppBreak:'Confidence breakdown',
    cbk:{evidence_completeness:'Evidence completeness',policy_clarity:'Policy clarity',precedent_alignment:'Precedent alignment',party_credibility:'Party credibility'},
    goodwill:'Goodwill credit', pendApproval:'AI recommendation, human approval required', recHead:'AI recommendation (not executed)',
    sfHead:'Safety case file for the human reviewer', sfInterim:'Suggested interim measures (policy 5.3)', sfNote:'The AI has not determined fault or recommended a resolution.',
    evLead:'Pulled evidence', evArgs:'Arguments', evResult:'Result', ok:'done', fail:'failed', pending:'…',
    noCase:'No case submitted', riderCase:'Rider case', driverCase:'Driver case', caseLabel:'Case submitted',
    claim:'Claim', ask:'Request', clauses:'Clauses', keyEv:'Key evidence',
    cbHead:"Rider's own words", cbTrip:'Trip', cbFoot:'No dispute type selected — the intake agent decides it',
    tgHead:'Intake result', tgConf:'Classification confidence', tgClaim:'Normalized claim', tgClaimed:'claimed',
    tgSigs:'Signals matched', tgFoot:id=>`Ticket ${id} filed, moving to the advocates`,
    snHead:'Evidence sufficiency check (deterministic rules, independent of the model)', snPoints:'Distinct evidence points',
    snCount:(c,t)=>`${c} / minimum ${t}`, snEmpty:'near-empty', snOk:'enough', snShort:'too few', snMet:'met',
    snTrig:'Override triggered → forced escalation to a human', snPass:"Not triggered — the model's ruling stands",
    snFlag:"Safety net override: evidence base too thin, forced escalation (the model's confidence does not count)",
    refund:'Refund', conf:'Confidence', escalated:'Escalated to a human', evTitle:'Evidence cited in verification',
    finalRuling:'Final ruling', elapsed:s=>`settled in ${s}s`, typingAria:'is working',
    maHead:ov=>`Model's independent assessment (judge agent's raw output${ov?', overridden by the safety net':''})`,
    maRuling:'Ruling', maRefund:'Refund',
    rl:{upheld:'Upheld (refund)', rejected:'Rejected', partial:'Partially upheld', escalated:'Escalated to human'},
    tl:{get_trip_data:'Trip data',get_gps_telemetry:'GPS',get_chat_logs:'Chat log',get_app_events:'App events',
        get_rider_profile:'Rider profile',get_driver_profile:'Driver profile',get_policy:'Policy',
        get_traffic_reference:'Traffic',get_fare_breakdown:'Fare breakdown',get_damage_evidence:'Damage photos',
        search_precedents:'Precedents'},
    rateLimit:'Real LLM quota / rate limit (429). Switch the backend at the top right to "Deterministic fallback" and run again: same flow, same tools, same rulings, only the reasoning steps are scripted.\n\n',
    tripAuto:'Auto-detect from my story', cbAuto:'Trip: auto-detect', chipVague:'Vague',
    cbFootAuto:'No dispute type or trip selected: the intake agent works both out from these words',
    tmMatched:(id, p, d)=>`Matched your trip ${id} (${p} to ${d})`, tmConf:'Match confidence', tmWhy:'Why this trip',
    tuPick:'Pick the trip and I will file the same words against it:', tuNone:'no matching details',
    tuScore:'score', st_completed:'completed', st_cancelled:'cancelled',
    tkHead:'Ticket filed', tkType:'Dispute type', tkAmount:'Claimed amount', tkRes:'Requested resolution', tkTrip:'Trip',
    tkFiled:'Filed', tkNotStated:'not stated', tkFacts:'Extracted from the story', tkMissing:'Would help, but not in the story',
    tkCheck:'Story vs platform records', tkCheckNote:'Informational only: this never changes the ruling.',
    tkJson:'View ticket JSON', tkNoFacts:'No specific facts stated', tkAutoMatched:'auto-matched',
    ccStatus:{consistent:'consistent', discrepancy:'discrepancy', not_in_record:'not in record'}, ccRecord:'record',
    fk:{quoted_amount:'Quoted / expected', charged_amount:'Charged', claimed_difference:'Difference claimed', fee_type:'Fee type',
        pickup_place:'Pickup', dropoff_place:'Drop-off', time_mentions:'Time', driver_actions:'Driver', rider_actions:'Rider',
        safety_indicators:'Safety indicators', detected_language:'Language'},
    fee:{cleaning_fee:'Cleaning fee', cancellation_fee:'Cancellation fee', damage_fee:'Damage fee'},
    langName:{en:'English', 'en-SG':'Singlish', ms:'Malay', ta:'Tamil', zh:'Chinese'},
  },
  zh: {
    tagline:'多智能体自主争议裁决 · 腾讯云 AI CAN DO IT 2026',
    loading:'载入中…', backendTitle:'选择驱动智能体的后端',
    beLlm:'实时 AI', beDet:'离线演示', offlineDemoTag:'离线演示（脚本化智能体）',
    presetTitle:'预置工单，一键重放', replay:'重放', replaying:'重放中…',
    fileHint:'用你自己的话写，系统自己判定争议类型',
    placeholder:'用你自己的话说说发生了什么…',
    tryHint:'试试：', chipEn:'英文', chipSl:'新加坡式英语', chipMs:'马来语', chipTa:'泰米尔语', chipZh:'中文',
    tripLbl:'关联行程', submit:'提交并裁决', ruling_btn:'裁决中…',
    fileFoot:'你的描述决定争议类型和行程；裁决依据平台自己的记录（GPS、聊天、车费、App 事件）。',
    a_intake:'受理分类智能体', a_rider:'乘客辩护智能体', a_driver:'司机辩护智能体', a_judge:'法官智能体', a_safety:'安全网校验',
    p_rider:'乘客', p_system:'政策引擎',
    idle:'待命', working:'取证中…', finished:'已完成', reasoning:'推理',
    emptyHint:'<strong>这里以群聊的方式裁决一场争议。</strong><br>'
      + '在下方输入框用你自己的话写下投诉，点「提交并裁决」。行程会根据你的描述自动匹配，也可以手动选择。<br>'
      + '受理智能体先判定争议类型，乘客方与司机方辩护智能体并行取证、各执一词，'
      + '法官再独立核验证据并给出裁决。'
      + '<span class="es-note">顶栏的下拉可重放预置工单。</span>',
    badgeLlm:(p,m)=>`${p} · ${m}`, badgeDet:'确定性回退 · 无需 API key', badgeFail:'健康检查失败',
    t_route:'绕路', t_noshow:'爽约', t_fare:'车费', t_property:'财物', t_safety:'安全', t_routeFull:'绕路多收费', t_noshowFull:'爽约取消费',
    chipFare:'车费争议', chipProp:'清洁费', chipSafe:'安全事件', a_safetycase:'安全案件材料',
    ppHead:'政策 v2.1 裁决路径', ppPath:{ai_final:'AI 终局裁决',ai_ruling_if_confident:'置信度足够时 AI 裁决',human_review:'人工复核'},
    ppReq:'所需置信度', ppFraud:'欺诈标记将门槛提高到 95%', ppClauses:'条款', ppBreak:'置信度构成',
    cbk:{evidence_completeness:'证据完整度',policy_clarity:'政策清晰度',precedent_alignment:'先例一致度',party_credibility:'当事人可信度'},
    goodwill:'善意补偿', pendApproval:'AI 建议，需人工批准', recHead:'AI 建议（未执行）',
    sfHead:'供人工复核的安全案件材料', sfInterim:'建议的临时措施（政策 5.3）', sfNote:'AI 未判定责任，也未建议处理方案。',
    evLead:'调取的证据', evArgs:'调用参数', evResult:'返回结果', ok:'完成', fail:'失败', pending:'…',
    noCase:'未提交案件', riderCase:'乘客方案件', driverCase:'司机方案件', caseLabel:'已提交案件',
    claim:'主张', ask:'诉求', clauses:'引用条款', keyEv:'关键证据',
    cbHead:'乘客原话', cbTrip:'行程', cbFoot:'未选择争议类型 —— 类型由受理分类智能体判定',
    tgHead:'受理分类结果', tgConf:'分类置信度', tgClaim:'归一化主张', tgClaimed:'主张',
    tgSigs:'命中信号', tgFoot:id=>`工单 ${id} 已建档，进入辩护阶段`,
    snHead:'证据充分性校验（确定性规则，与模型无关）', snPoints:'独立数据点',
    snCount:(c,t)=>`${c} / 下限 ${t}`, snEmpty:'空或近空', snOk:'充足', snShort:'不足', snMet:'达标',
    snTrig:'触发覆盖 → 强制升级人工', snPass:'未触发 —— 维持模型裁决',
    snFlag:'安全网覆盖：证据基础不足，强制升级人工（模型置信度不作数）',
    refund:'退费', conf:'置信度', escalated:'已升级人工', evTitle:'核验引用的证据',
    finalRuling:'最终裁决', elapsed:s=>`${s} 秒完成`, typingAria:'正在处理',
    maHead:ov=>`模型独立判断（法官智能体原始输出${ov?'，已被安全网覆盖':''}）`,
    maRuling:'裁决', maRefund:'退款',
    rl:{upheld:'支持（退费）', rejected:'驳回', partial:'部分支持', escalated:'升级人工'},
    tl:{get_trip_data:'行程数据',get_gps_telemetry:'GPS',get_chat_logs:'聊天记录',get_app_events:'App 事件',
        get_rider_profile:'乘客档案',get_driver_profile:'司机档案',get_policy:'政策条款',
        get_traffic_reference:'路况参考',get_fare_breakdown:'费用明细',get_damage_evidence:'损坏证据',
        search_precedents:'先例检索'},
    rateLimit:'真实 LLM 额度/限流（429）。请把右上角后端切换为「确定性回退」再跑一次 —— 流程、工具与裁决结果完全一致，只是推理步骤由剧本驱动。\n\n',
    tripAuto:'根据我的描述自动识别', cbAuto:'行程：自动识别', chipVague:'描述含糊',
    cbFootAuto:'未选择争议类型和行程：受理智能体会从这段话里判断',
    tmMatched:(id, p, d)=>`已匹配到你的行程 ${id}（${p} 至 ${d}）`, tmConf:'匹配置信度', tmWhy:'匹配依据',
    tuPick:'请选择行程，我会用同一段话针对该行程建档：', tuNone:'无匹配细节',
    tuScore:'得分', st_completed:'已完成', st_cancelled:'已取消',
    tkHead:'工单已建档', tkType:'争议类型', tkAmount:'主张金额', tkRes:'诉求', tkTrip:'行程',
    tkFiled:'建档时间', tkNotStated:'未提及', tkFacts:'从描述中提取的事实', tkMissing:'有帮助但描述中未提及',
    tkCheck:'描述与平台记录对照', tkCheckNote:'仅供参考：不会影响裁决。',
    tkJson:'查看工单 JSON', tkNoFacts:'未提及具体事实', tkAutoMatched:'自动匹配',
    ccStatus:{consistent:'一致', discrepancy:'不一致', not_in_record:'记录中无此项'}, ccRecord:'记录',
    fk:{quoted_amount:'报价 / 预期', charged_amount:'被收取', claimed_difference:'主张差额', fee_type:'费用类型',
        pickup_place:'上车点', dropoff_place:'下车点', time_mentions:'时间', driver_actions:'司机', rider_actions:'乘客',
        safety_indicators:'安全指标', detected_language:'语言'},
    fee:{cleaning_fee:'清洁费', cancellation_fee:'取消费', damage_fee:'损坏费'},
    langName:{en:'英语', 'en-SG':'新加坡式英语', ms:'马来语', ta:'泰米尔语', zh:'中文'},
  },
};
const CUR = 'S$';

/* Embedded mode (three-pane page): only the agent-room renderer is used; the page wires everything else. */
const EMBED = !!window.RR_EMBED;

let LANG = 'en';
try { const s = localStorage.getItem('rr_lang'); if (s === 'zh' || s === 'en') LANG = s; } catch (e) {}
const T = k => (I18N[LANG][k] !== undefined ? I18N[LANG][k] : I18N.en[k]);
const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

/* ---------------------------------------------------------------- participants */
const PARTICIPANTS = {
  rider:           {ini:'R',  key:'p_rider',      side:'left'},
  intake:          {ini:'IN', key:'a_intake',     side:'center'},
  rider_advocate:  {ini:'RA', key:'a_rider',      side:'left'},
  driver_advocate: {ini:'DA', key:'a_driver',     side:'right'},
  judge:           {ini:'J',  key:'a_judge',      side:'center'},
  safety_net:      {ini:'SN', key:'a_safety',     side:'center'},
  safety_case:     {ini:'SC', key:'a_safetycase', side:'center'},
  system:          {ini:'PY', key:'p_system',     side:'center'},
};
const ROSTER = ['rider','intake','rider_advocate','driver_advocate','judge','safety_net'];
const partName = w => T((PARTICIPANTS[w] || PARTICIPANTS.system).key);
const toolLabel = t => (T('tl') || {})[t] || t;
/* Confidence scores arrive as 1, 0.92, 0.5 … — show them all to two decimals. */
const conf2 = v => (typeof v === 'number' && isFinite(v)) ? v.toFixed(2) : String(v);

const el = id => document.getElementById(id);
const chat = el('chat'), typingZone = el('typingZone'), roster = el('roster');
const runBtn = el('runBtn'), fileBtn = el('fileBtn');
const sel = el('disputeSelect'), tripSel = el('tripSelect');
const complaintInput = el('complaintInput'), modeBadge = el('modeBadge');
const backendSelect = el('backendSelect'), offlineTag = el('offlineTag');

let health = null, disputes = [], trips = [];
let busy = null;                 // 'file' | 'run' | null
let bubbleFor = {};              // agent -> the bubble that currently collects its evidence chips
let pendingChips = {};           // agent -> chips still waiting for a tool_result
let typingEls = {};              // agent -> typing indicator element

function typeLabel(t){
  const m = {route_deviation:'t_route',no_show_charge:'t_noshow',fare_dispute:'t_fare',property_damage:'t_property',safety_incident:'t_safety'};
  return m[t] ? T(m[t]) : t;
}
const rulingLabel = r => (T('rl') || {})[r] || r;

/* ---------------------------------------------------------------- static chrome */
function applyStatic(){
  document.documentElement.lang = LANG === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach(n => { n.textContent = T(n.dataset.i18n); });
  document.querySelectorAll('[data-i18n-html]').forEach(n => { n.innerHTML = T(n.dataset.i18nHtml); });
  document.querySelectorAll('[data-i18n-title]').forEach(n => { n.title = T(n.dataset.i18nTitle); });
  document.querySelectorAll('[data-i18n-ph]').forEach(n => { n.placeholder = T(n.dataset.i18nPh); });
  document.querySelectorAll('#langToggle button').forEach(b => b.classList.toggle('on', b.dataset.lang === LANG));
  document.title = EMBED ? T('tpTitle') : (LANG === 'zh' ? 'RydeResolve | 多智能体争议裁决' : 'RydeResolve | Multi-agent dispute resolution');
  renderBadge(); renderDropdowns(); renderRoster();
  if (fileBtn && busy !== 'file') fileBtn.textContent = T('submit');
  if (runBtn && busy !== 'run') runBtn.textContent = T('replay');
}

function renderBadge(){
  if (!health || !modeBadge) return;
  const llm = health.llm_mode === 'llm';
  modeBadge.textContent = llm ? T('badgeLlm')(health.llm_provider || 'LLM', health.model || health.hunyuan_model) : T('badgeDet');
  modeBadge.className = 'mode-badge ' + (llm ? 'llm' : 'det');
  const hasKey = health.has_api_key !== false;
  backendSelect.hidden = !hasKey;
  offlineTag.hidden = hasKey;
}

function renderDropdowns(){
  if (!sel || !tripSel) return;
  const cur = sel.value, curT = tripSel.value;
  sel.innerHTML = ''; tripSel.innerHTML = '';
  disputes.forEach(x => {
    const o = document.createElement('option'); o.value = x.dispute_id;
    o.textContent = `${x.dispute_id} · ${typeLabel(x.dispute_type)} · ${x.description.slice(0,24)}…`;
    sel.appendChild(o);
  });
  const auto = document.createElement('option'); auto.value = 'auto'; auto.textContent = T('tripAuto');
  tripSel.appendChild(auto);
  trips.forEach(x => {
    const o = document.createElement('option'); o.value = x.trip_id;
    o.textContent = `${x.trip_id} · ${x.route}${x.outcome ? ' · ' + x.outcome : ''}`;
    tripSel.appendChild(o);
  });
  if (cur) sel.value = cur; tripSel.value = curT || 'auto';
}

/* Participant strip: who is in this chat, and who is working right now. */
function renderRoster(){
  if (!roster) return;
  const state = {};
  roster.querySelectorAll('.roster-item').forEach(n => {
    state[n.dataset.who] = n.classList.contains('active') ? 'active' : (n.classList.contains('done') ? 'done' : '');
  });
  roster.innerHTML = '';
  ROSTER.forEach(w => {
    const p = PARTICIPANTS[w];
    const d = document.createElement('div');
    d.className = `roster-item who-${w} ${state[w] || ''}`.trim();
    d.dataset.who = w;
    d.innerHTML = '<span class="av" aria-hidden="true"></span><span class="roster-name"></span>';
    d.querySelector('.av').textContent = p.ini;
    d.querySelector('.roster-name').textContent = partName(w);
    roster.appendChild(d);
  });
}
function setRoster(who, status){
  const n = roster.querySelector(`.roster-item[data-who="${who}"]`); if (!n) return;
  n.classList.toggle('active', status === 'active');
  if (status === 'done') n.classList.add('done');
}

/* ---------------------------------------------------------------- scrolling */
let stick = true, scrollQueued = false;
/* The classic page scrolls the window; the three-pane page scrolls the room pane's own container. */
const SCROLLER = document.querySelector('[data-room-scroll]');
const atBottom = () => SCROLLER
  ? SCROLLER.scrollTop + SCROLLER.clientHeight >= SCROLLER.scrollHeight - 160
  : (window.innerHeight + window.scrollY) >= document.documentElement.scrollHeight - 260;
/* Only a deliberate scroll by the reader detaches the view; the smooth scrolling we do
   ourselves fires plenty of mid-flight scroll events and must not switch following off. */
const scrollHost = SCROLLER || window;
['wheel','touchmove','keydown'].forEach(t =>
  scrollHost.addEventListener(t, () => { stick = atBottom(); }, {passive:true}));
scrollHost.addEventListener('scroll', () => { if (atBottom()) stick = true; }, {passive:true});
function autoscroll(){
  if (!stick || scrollQueued) return;
  scrollQueued = true;
  requestAnimationFrame(() => {
    scrollQueued = false;
    if (SCROLLER) SCROLLER.scrollTo({top: SCROLLER.scrollHeight, behavior:'smooth'});
    else window.scrollTo({top: document.documentElement.scrollHeight, behavior:'smooth'});
  });
}

/* ---------------------------------------------------------------- chat primitives */
function append(node){ chat.insertBefore(node, typingZone); autoscroll(); }

function msgRow(who, label){
  const p = PARTICIPANTS[who] || PARTICIPANTS.system;
  const row = document.createElement('div');
  row.className = `msg ${p.side} who-${who}`;
  const av = document.createElement('div');
  av.className = 'av'; av.textContent = p.ini; av.setAttribute('aria-hidden','true');
  const stack = document.createElement('div'); stack.className = 'stack';
  const meta = document.createElement('div'); meta.className = 'meta';
  const nm = document.createElement('span'); nm.className = 'nm'; nm.textContent = partName(who);
  meta.appendChild(nm);
  if (label){ const pl = document.createElement('span'); pl.className = 'pill'; pl.textContent = label; meta.appendChild(pl); }
  stack.appendChild(meta);
  row.appendChild(av); row.appendChild(stack);
  return {row, stack};
}

function bubble(stack, extraCls){
  const b = document.createElement('div');
  b.className = 'bubble' + (extraCls ? ' ' + extraCls : '');
  stack.appendChild(b);
  return b;
}

function addDivider(text){
  const d = document.createElement('div'); d.className = 'divider';
  const s = document.createElement('span'); s.textContent = text;
  d.appendChild(s); append(d);
}

/* Consecutive messages from the same agent stay in one bubble (and share one evidence
   row) until the agent finishes or the phase moves on — otherwise a scripted run turns
   into a wall of one-line bubbles. */
function appendLine(b, text){
  const p = document.createElement('p'); p.className = 'line'; p.textContent = text;
  const ev = b.querySelector(':scope > .evidence');
  if (ev) b.insertBefore(p, ev); else b.appendChild(p);
}
function openBubble(agent){
  const b = bubbleFor[agent];
  return (b && b.isConnected && !b.dataset.sealed) ? b : null;
}
function seal(agent){
  const b = bubbleFor[agent];
  if (b) b.dataset.sealed = '1';
  delete bubbleFor[agent];
}
function sealAll(){ Object.keys(bubbleFor).forEach(seal); }

function addThinking(agent, content){
  let b = openBubble(agent);
  if (b){ appendLine(b, content); autoscroll(); return b; }
  const who = PARTICIPANTS[agent] ? agent : 'system';
  const {row, stack} = msgRow(who);
  b = bubble(stack);
  appendLine(b, content);
  append(row);
  bubbleFor[agent] = b;
  return b;
}

/* ---------------------------------------------------------------- evidence chips */
/* Tool calls never get their own row: they collapse into a "pulled evidence" line
   inside the bubble the agent is currently speaking from. Consecutive calls from the
   same agent share one chip row; a new reasoning message starts a new one. */
function evidenceHost(agent){
  let b = openBubble(agent);
  if (!b){
    const who = PARTICIPANTS[agent] ? agent : 'system';
    const {row, stack} = msgRow(who);
    b = bubble(stack, 'bare');
    append(row);
    bubbleFor[agent] = b;
  }
  let ev = b.querySelector(':scope > .evidence');
  if (!ev){
    ev = document.createElement('div'); ev.className = 'evidence';
    const head = document.createElement('div'); head.className = 'ev-head';
    const lead = document.createElement('span'); lead.className = 'ev-lead'; lead.textContent = T('evLead');
    head.appendChild(lead);
    const chips = document.createElement('div'); chips.className = 'ev-chips';
    ev.appendChild(head); ev.appendChild(chips);
    b.appendChild(ev);
  }
  return ev;
}

function renderPanel(ev, chip){
  const old = ev.querySelector('.ev-panel'); if (old) old.remove();
  const p = document.createElement('div'); p.className = 'ev-panel';
  const mk = (k, body) => {
    const r = document.createElement('div'); r.className = 'ep-row';
    const ks = document.createElement('span'); ks.className = 'ep-k'; ks.textContent = k;
    const pre = document.createElement('pre'); pre.textContent = body;
    r.appendChild(ks); r.appendChild(pre); return r;
  };
  p.appendChild(mk(`${chip._tool} · ${T('evArgs')}`, JSON.stringify(chip._args || {}, null, 2)));
  p.appendChild(mk(T('evResult'), chip._result == null ? T('pending') : JSON.stringify(chip._result, null, 2)));
  ev.appendChild(p);
}

function toggleChip(ev, chip){
  const wasOpen = chip.getAttribute('aria-expanded') === 'true';
  ev.querySelectorAll('.ev-chip[aria-expanded="true"]').forEach(c => c.setAttribute('aria-expanded','false'));
  const old = ev.querySelector('.ev-panel'); if (old) old.remove();
  if (wasOpen) return;
  chip.setAttribute('aria-expanded','true');
  renderPanel(ev, chip);
  autoscroll();
}

function addToolCall(agent, tool, args){
  const ev = evidenceHost(agent);
  const chip = document.createElement('button');
  chip.type = 'button'; chip.className = 'ev-chip';
  chip.dataset.state = 'pending'; chip.setAttribute('aria-expanded','false');
  const st = document.createElement('span'); st.className = 'st';
  const lb = document.createElement('span'); lb.className = 'lb'; lb.textContent = toolLabel(tool);
  chip.appendChild(st); chip.appendChild(lb);
  chip._tool = tool; chip._args = args; chip._result = null;
  chip.addEventListener('click', () => toggleChip(ev, chip));
  ev.querySelector('.ev-chips').appendChild(chip);
  (pendingChips[agent] = pendingChips[agent] || []).push(chip);
  autoscroll();
}

function addToolResult(agent, tool, ok, result){
  const q = pendingChips[agent] || [];
  const i = q.findIndex(c => c._tool === tool && c.dataset.state === 'pending');
  if (i < 0) return;
  const chip = q.splice(i, 1)[0];
  chip.dataset.state = ok ? 'ok' : 'fail';
  chip._result = result;
  chip.title = `${toolLabel(tool)} · ${ok ? T('ok') : T('fail')}`;
  if (chip.getAttribute('aria-expanded') === 'true') renderPanel(chip.closest('.evidence'), chip);
}

/* ---------------------------------------------------------------- typing indicator */
function showTyping(agent){
  const p = PARTICIPANTS[agent];
  if (!p || typingEls[agent]) return;
  const t = document.createElement('div');
  t.className = `typing who-${agent}` + (p.side === 'right' ? ' right' : '');
  t.setAttribute('aria-label', `${partName(agent)} ${T('typingAria')}`);
  const av = document.createElement('div'); av.className = 'av'; av.textContent = p.ini; av.setAttribute('aria-hidden','true');
  const dots = document.createElement('div'); dots.className = 'dots';
  dots.innerHTML = '<i></i><i></i><i></i>';
  t.appendChild(av); t.appendChild(dots);
  typingZone.appendChild(t); typingEls[agent] = t;
  autoscroll();
}
function hideTyping(agent){ const t = typingEls[agent]; if (t){ t.remove(); delete typingEls[agent]; } }
function hideAllTyping(){ Object.keys(typingEls).forEach(hideTyping); }

/* ---------------------------------------------------------------- message cards */
function kvList(rows){
  const w = document.createElement('div'); w.className = 'kv-list';
  rows.forEach(([k, v, isNode]) => {
    const r = document.createElement('div'); r.className = 'kv';
    const ks = document.createElement('span'); ks.className = 'k'; ks.textContent = k;
    const vs = document.createElement('span'); vs.className = 'v';
    if (isNode) vs.appendChild(v); else vs.textContent = v;
    r.appendChild(ks); r.appendChild(vs); w.appendChild(r);
  });
  return w;
}
function tagList(items, cls){
  const w = document.createElement('div'); w.className = 'taglist';
  (items || []).forEach(x => { const t = document.createElement('span'); t.className = 'tag' + (cls ? ' ' + cls : ''); t.textContent = x; w.appendChild(t); });
  return w;
}
function bullets(items, cls){
  const ul = document.createElement('ul'); ul.className = 'bullets' + (cls ? ' ' + cls : '');
  (items || []).forEach(x => { const li = document.createElement('li'); li.textContent = x; ul.appendChild(li); });
  return ul;
}
function section(title, node){
  const s = document.createElement('div'); s.className = 'sub';
  const h = document.createElement('h4'); h.textContent = title;
  s.appendChild(h); s.appendChild(node); return s;
}
function heading(text){ const h = document.createElement('h4'); h.textContent = text; return h; }

let complaintShown = false;
function addComplaint(text, tripId, foot){
  const {row, stack} = msgRow('rider', tripId ? `${T('cbTrip')} ${tripId}` : T('cbAuto'));
  const b = bubble(stack, 'complaint');
  const q = document.createElement('div'); q.className = 'c-quote'; q.textContent = text;
  const f = document.createElement('div'); f.className = 'c-foot'; f.textContent = foot || (tripId ? T('cbFoot') : T('cbFootAuto'));
  b.appendChild(q); b.appendChild(f);
  append(row);
  complaintShown = true;
  setRoster('rider', 'done');
}

/* ---- story -> trip */
const splitRoute = r => { const p = String(r || '').split(' → '); return [p[0] || '?', p[1] || '?']; };
function fmtTime(iso){
  if (!iso) return '';
  const d = new Date(iso); if (isNaN(d)) return iso;
  return d.toLocaleString(LANG === 'zh' ? 'zh-CN' : 'en-SG',
    {timeZone:'Asia/Singapore', day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'});
}

function addTripMatched(ev){
  const {row, stack} = msgRow('intake');
  const b = bubble(stack, 'card trip-match');
  const [p, d] = splitRoute(ev.route);
  const line = document.createElement('p'); line.className = 'tm-line'; line.textContent = T('tmMatched')(ev.trip_id, p, d);
  b.appendChild(line);
  const meta = document.createElement('div'); meta.className = 'panel-line';
  meta.innerHTML = `${esc(T('tmConf'))} <b>${esc(conf2(ev.confidence))}</b>`;
  b.appendChild(meta);
  if ((ev.reasons || []).length) b.appendChild(section(T('tmWhy'), tagList(ev.reasons, 'blue')));
  append(row);
}

function addTripUnresolved(ev){
  const {row, stack} = msgRow('intake');
  const b = bubble(stack, 'card trip-pick-card');
  const msg = document.createElement('p'); msg.className = 'tm-line'; msg.textContent = ev.message || '';
  b.appendChild(msg);
  b.appendChild(note(T('tuPick')));
  const list = document.createElement('div'); list.className = 'cand-list';
  (ev.candidates || []).forEach(c => {
    const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'cand';
    const [p, d] = splitRoute(c.route);
    const top = document.createElement('span'); top.className = 'cand-route'; top.textContent = `${p} → ${d}`;
    const sub = document.createElement('span'); sub.className = 'cand-sub';
    sub.textContent = [c.trip_id, fmtTime(c.time), T('st_' + c.status) || c.status].filter(Boolean).join(' · ');
    btn.appendChild(top); btn.appendChild(sub);
    if ((c.reasons || []).length) btn.appendChild(tagList(c.reasons.slice(0, 3)));
    btn.addEventListener('click', () => {
      if (window.RR_PICK_TRIP) window.RR_PICK_TRIP(c.trip_id, `${p} → ${d}`);
      else if (!busy) resubmitWithTrip(c.trip_id);
    });
    list.appendChild(btn);
  });
  b.appendChild(list);
  append(row);
  seal('intake');
}

/* ---- the filed ticket, in the official format */
let lastTriage = null;
function money(v){ return (typeof v === 'number' && isFinite(v)) ? CUR + v.toFixed(2) : String(v); }
function factValue(k, v){
  if (Array.isArray(v)) return v.length ? tagList(v) : null;
  if (v == null || v === '') return null;
  if (/_amount$|_difference$/.test(k)) return money(v);
  if (k === 'fee_type') return (T('fee') || {})[v] || v;
  if (k === 'detected_language') return (T('langName') || {})[v] || v;
  return String(v);
}

function addTicket(ev){
  const t = ev.ticket || {}, f = t.extracted_facts || {}, tr = lastTriage || {};
  const {row, stack} = msgRow('intake', t.dispute_id);
  const b = bubble(stack, 'card ticket');
  b.appendChild(heading(T('tkHead')));
  const line = document.createElement('div'); line.className = 'panel-line';
  const badge = document.createElement('span'); badge.className = 'tag rose';
  badge.textContent = ev.dispute_type_label || typeLabel(t.dispute_type);
  const raw = document.createElement('span'); raw.className = 't-type'; raw.textContent = t.dispute_type;
  const cf = document.createElement('span');
  const conf = ev.classification_confidence != null ? ev.classification_confidence : tr.classification_confidence;
  cf.innerHTML = `${esc(T('tgConf'))} <b>${esc(conf2(conf))}</b>`;
  line.appendChild(badge); line.appendChild(raw); line.appendChild(cf);
  b.appendChild(line);

  const tm = ev.trip_match, ts = ev.trip_summary;
  const trip = t.trip_id + (tm ? ` · ${tm.route} · ${T('tkAutoMatched')} ${conf2(tm.confidence)}`
    : (ts && ts.route ? ` · ${ts.route}${ts.time ? ' · ' + fmtTime(ts.time) : ''}` : ''));
  const kv = kvList([
    [T('tkAmount'), t.requested_amount != null ? money(t.requested_amount) : T('tkNotStated')],
    [T('tkRes'), t.requested_resolution || '-'],
    [T('tkTrip'), trip],
    [T('tkFiled'), fmtTime(t.filed_at)],
  ]);
  kv.classList.add('tk-kv');
  b.appendChild(kv);
  if (tr.classification_reasoning) b.appendChild(note(tr.classification_reasoning));
  const sigs = ev.detected_signals || tr.detected_signals || [];
  if (sigs.length) b.appendChild(section(T('tgSigs'), tagList(sigs)));

  const rows = [];
  Object.keys(T('fk')).forEach(k => {
    const v = factValue(k, f[k]);
    if (v != null) rows.push([(T('fk') || {})[k] || k, v, typeof v !== 'string']);
  });
  b.appendChild(section(T('tkFacts'), rows.length ? kvList(rows) : note(T('tkNoFacts'))));

  if ((t.missing_info || []).length) b.appendChild(section(T('tkMissing'), bullets(t.missing_info)));

  if ((t.claim_check || []).length){
    const box = document.createElement('div'); box.className = 'sn-rows cc-rows';
    t.claim_check.forEach(c => {
      const r = document.createElement('div'); r.className = 'sn-row';
      const ks = document.createElement('span'); ks.className = 'sk'; ks.textContent = c.label || c.claim;
      const unit = /speed|distance/.test(c.claim) ? (v => String(v)) : money;
      const vs = document.createElement('span'); vs.className = 'sv';
      vs.textContent = unit(c.story_value) + (c.record_value != null ? `  ·  ${T('ccRecord')} ${unit(c.record_value)}` : '');
      const fs = document.createElement('span');
      fs.className = 'sf ' + (c.status === 'consistent' ? 'good' : c.status === 'discrepancy' ? 'bad' : 'na');
      fs.textContent = (T('ccStatus') || {})[c.status] || c.status;
      r.appendChild(ks); r.appendChild(vs); r.appendChild(fs); box.appendChild(r);
    });
    const s = section(T('tkCheck'), box);
    s.appendChild(note(T('tkCheckNote')));
    b.appendChild(s);
  }

  const det = document.createElement('details'); det.className = 'tk-json';
  const sum = document.createElement('summary'); sum.textContent = T('tkJson');
  const pre = document.createElement('pre'); pre.textContent = JSON.stringify(t, null, 2);
  det.appendChild(sum); det.appendChild(pre);
  b.appendChild(det);
  append(row);
  seal('intake');
}

/* A later message from the rider (a reply to support, or which trip it was). */
function addRiderMessage(text){
  sealAll();
  const {row, stack} = msgRow('rider');
  const b = bubble(stack, 'complaint');
  const q = document.createElement('div'); q.className = 'c-quote'; q.textContent = text;
  b.appendChild(q);
  append(row);
}

function addCaseCard(who, c){
  const {row, stack} = msgRow(who, c ? T('caseLabel') : null);
  const b = bubble(stack, 'card case-card');
  b.appendChild(heading(who === 'rider_advocate' ? T('riderCase') : T('driverCase')));
  if (!c){
    const p = document.createElement('p'); p.className = 'note'; p.textContent = T('noCase');
    b.appendChild(p); append(row); return;
  }
  const ask = c.requested_outcome + (c.requested_amount != null ? ` · ${CUR}${c.requested_amount}` : '');
  b.appendChild(kvList([
    [T('claim'), c.claim],
    [T('ask'), ask],
    [T('clauses'), tagList((c.policy_clauses_referenced || []).length ? c.policy_clauses_referenced : ['-']), true],
  ]));
  if ((c.evidence_cited || []).length) b.appendChild(section(T('keyEv'), bullets(c.evidence_cited)));
  append(row);
}

function addSafetyNet(sn){
  const existing = openBubble('safety_net');
  let b, row = null;
  if (existing){ b = existing; b.classList.add('card'); b.classList.remove('bare'); }
  else { const m = msgRow('safety_net'); row = m.row; b = bubble(m.stack, 'card'); }
  const parts = document.createDocumentFragment();
  parts.appendChild(heading(T('snHead')));
  const chk = sn.checks || {}, src = chk.evidence_sources || {};
  const rows = document.createElement('div'); rows.className = 'sn-rows';
  const mkRow = (k, v, okFlag, flagTxt) => {
    const r = document.createElement('div'); r.className = 'sn-row';
    const ks = document.createElement('span'); ks.className = 'sk'; ks.textContent = k;
    const vs = document.createElement('span'); vs.className = 'sv'; vs.textContent = v;
    const fs = document.createElement('span'); fs.className = 'sf ' + (okFlag ? 'good' : 'bad'); fs.textContent = flagTxt;
    r.appendChild(ks); r.appendChild(vs); r.appendChild(fs); rows.appendChild(r);
  };
  const short = chk.distinct_evidence_points < chk.min_evidence_points;
  mkRow(T('snPoints'), T('snCount')(chk.distinct_evidence_points, chk.min_evidence_points), !short, short ? T('snShort') : T('snMet'));
  Object.keys(src).forEach(k => {
    const i = src[k];
    mkRow(k, T('snCount')(i.count, i.threshold), !i.near_empty, i.near_empty ? T('snEmpty') : T('snOk'));
  });
  parts.appendChild(rows);
  if ((sn.reasons || []).length){
    const ul = bullets(sn.reasons); ul.classList.add('sn-reasons');
    parts.appendChild(ul);
  }
  const v = document.createElement('div');
  v.className = 'sn-verdict ' + (sn.triggered ? 'trig' : 'pass');
  v.textContent = sn.triggered ? T('snTrig') : T('snPass');
  parts.appendChild(v);
  const ev = b.querySelector(':scope > .evidence');
  if (ev) b.insertBefore(parts, ev); else b.appendChild(parts);
  if (row) append(row); else autoscroll();
}

function addError(ev){
  let msg = (ev.message || '') + '\n' + (ev.trace || '');
  if (/429|quota|rate|RESOURCE_EXHAUSTED/i.test(msg)) msg = T('rateLimit') + msg;
  const d = document.createElement('div'); d.className = 'err-box'; d.textContent = msg.trim();
  append(d);
}

/* ---------------------------------------------------------------- ruling card */
function metric(label, value, money){
  const d = document.createElement('div'); d.className = 'metric' + (money ? ' money' : '');
  const k = document.createElement('span'); k.className = 'mk'; k.textContent = label;
  const v = document.createElement('span'); v.className = 'mv'; v.textContent = value;
  d.appendChild(k); d.appendChild(v); return d;
}
function panel(title){
  const p = document.createElement('div'); p.className = 'panel';
  p.appendChild(heading(title)); return p;
}
function note(text){ const p = document.createElement('p'); p.className = 'note'; p.textContent = text; return p; }

function addRuling(r, elapsedMs){
  const sn = r.safety_net || null, ma = r.model_assessment || null;
  const card = document.createElement('article');
  const cls = {upheld:'r-upheld',rejected:'r-rejected',partial:'r-partial',escalated:'r-escalated'}[r.ruling] || 'r-partial';
  card.className = 'ruling ' + cls;

  const strip = document.createElement('div'); strip.className = 'r-strip';
  const body = document.createElement('div'); body.className = 'r-body';
  card.appendChild(strip); card.appendChild(body);

  /* header: badge + metrics */
  const top = document.createElement('div'); top.className = 'r-top';
  const lab = document.createElement('span'); lab.className = 'r-label';
  lab.textContent = T('finalRuling');
  if (elapsedMs >= 200){
    const t = document.createElement('span'); t.className = 'r-elapsed';
    t.textContent = ' · ' + T('elapsed')((elapsedMs / 1000).toFixed(1));
    lab.appendChild(t);
  }
  top.appendChild(lab);
  const badge = document.createElement('span'); badge.className = 'r-badge'; badge.textContent = rulingLabel(r.ruling);
  top.appendChild(badge);
  const flagTxt = r.ruling === 'escalated' ? T('escalated') : (r.escalation_required ? T('pendApproval') : '');
  if (flagTxt){ const t = document.createElement('span'); t.className = 'tag'; t.textContent = flagTxt; top.appendChild(t); }
  const mw = document.createElement('div'); mw.className = 'r-metrics';
  if (r.refund_amount != null) mw.appendChild(metric(T('refund'), CUR + r.refund_amount, true));
  if (r.goodwill_credit) mw.appendChild(metric(T('goodwill'), CUR + r.goodwill_credit, true));
  if (r.confidence_score != null) mw.appendChild(metric(T('conf'), conf2(r.confidence_score)));
  if (mw.children.length) top.appendChild(mw);
  body.appendChild(top);

  if (sn && sn.triggered){
    const n = document.createElement('div'); n.className = 'r-note'; n.textContent = T('snFlag');
    body.appendChild(n);
  }

  const reason = document.createElement('p'); reason.className = 'r-reason'; reason.textContent = r.reasoning || '';
  body.appendChild(reason);

  if ((r.evidence_cited || []).length){
    const p = panel(T('evTitle'));
    p.appendChild(bullets(r.evidence_cited, 'check'));
    body.appendChild(p);
  }

  /* policy path + confidence breakdown */
  const pp = r.policy_path;
  if (pp){
    const p = panel(T('ppHead'));
    const line = document.createElement('div'); line.className = 'panel-line';
    const b1 = document.createElement('span'); b1.className = 'tag blue';
    b1.textContent = (T('ppPath') || {})[pp.path] || pp.path;
    line.appendChild(b1);
    const cl = document.createElement('span');
    cl.textContent = `${T('ppClauses')}: ${(r.policy_clauses || []).join(', ') || pp.clause || '-'}`;
    line.appendChild(cl);
    if (pp.required_confidence != null){
      const rc = document.createElement('span');
      rc.innerHTML = `${esc(T('ppReq'))} <b>${esc(conf2(pp.required_confidence))}</b>`;
      line.appendChild(rc);
    }
    p.appendChild(line);
    if (pp.fraud_flag) p.appendChild(note(T('ppFraud')));
    (pp.reasons || []).forEach(x => p.appendChild(note(x)));
    if (r.confidence_breakdown){
      const h = document.createElement('h4'); h.textContent = T('ppBreak');
      h.style.margin = '14px 0 0';
      p.appendChild(h);
      const bars = document.createElement('div'); bars.className = 'bars';
      Object.keys(r.confidence_breakdown).forEach(k => {
        const val = Number(r.confidence_breakdown[k]);
        const row = document.createElement('div'); row.className = 'bar';
        const bl = document.createElement('span'); bl.className = 'bl'; bl.textContent = (T('cbk') || {})[k] || k;
        const bt = document.createElement('span'); bt.className = 'bt';
        const bf = document.createElement('span'); bf.className = 'bf';
        bf.style.width = Math.max(0, Math.min(100, (isFinite(val) ? val : 0) * 100)) + '%';
        bt.appendChild(bf);
        const bv = document.createElement('span'); bv.className = 'bv';
        bv.textContent = isFinite(val) ? val.toFixed(2) : String(r.confidence_breakdown[k]);
        row.appendChild(bl); row.appendChild(bt); row.appendChild(bv);
        bars.appendChild(row);
      });
      p.appendChild(bars);
    }
    body.appendChild(p);
  }

  /* AI recommendation (not executed) */
  if (r.recommendation){
    const p = panel(T('recHead'));
    p.appendChild(kvList([
      [T('maRuling'), rulingLabel(r.recommendation.ruling)],
      [T('maRefund'), r.recommendation.refund_amount != null ? CUR + r.recommendation.refund_amount : '-'],
    ]));
    body.appendChild(p);
  }

  /* safety case file */
  if (r.case_file){
    const p = panel(T('sfHead'));
    p.appendChild(bullets(r.case_file.facts));
    p.appendChild(section(T('sfInterim'), bullets(r.case_file.interim_measures)));
    p.appendChild(note(T('sfNote')));
    body.appendChild(p);
  }

  /* the model's own assessment, kept even when the safety net overrode it */
  if (ma){
    const p = panel(T('maHead')(sn && sn.triggered));
    p.appendChild(kvList([
      [T('maRuling'), rulingLabel(ma.ruling)],
      [T('maRefund'), ma.refund_amount != null ? CUR + ma.refund_amount : '-'],
      [T('conf'), ma.confidence_score != null ? conf2(ma.confidence_score) : '-'],
    ]));
    if (ma.reasoning) p.appendChild(note(ma.reasoning));
    if ((ma.evidence_cited || []).length) p.appendChild(section(T('evTitle'), bullets(ma.evidence_cited)));
    body.appendChild(p);
  }

  if (r.escalation_required && r.escalation_summary){
    const e = document.createElement('div'); e.className = 'esc-box'; e.textContent = r.escalation_summary;
    body.appendChild(e);
  }

  append(card);
}

/* ---------------------------------------------------------------- event -> chat */
function render(ev){
  switch (ev.type){
    case 'phase':
      sealAll();
      if (ev.message) addDivider(ev.message);
      if (ev.phase === 'intake'){
        // A preset replay has no complaint_received event: the rider's own words
        // arrive on the ticket, and they still open the conversation.
        if (!complaintShown && ev.ticket && ev.ticket.description){
          const t = ev.ticket;
          const amt = t.requested_amount != null ? ` · ${T('tgClaimed')} ${CUR}${t.requested_amount}` : '';
          addComplaint(t.description, t.trip_id, typeLabel(t.dispute_type) + amt);
        }
        setRoster('intake','active');
        if (!complaintShown) showTyping('intake');
      }
      else if (ev.phase === 'safety_intake'){ setRoster('intake','done'); setRoster('safety_net','active'); showTyping('safety_case'); }
      else if (ev.phase === 'advocates'){
        setRoster('intake','done');
        setRoster('rider_advocate','active'); setRoster('driver_advocate','active');
        showTyping('rider_advocate'); showTyping('driver_advocate');
      }
      else if (ev.phase === 'cases_submitted'){
        hideTyping('rider_advocate'); hideTyping('driver_advocate');
        setRoster('rider_advocate','done'); setRoster('driver_advocate','done');
        queue.unshift({type:'_case', who:'rider_advocate', case: ev.rider_case},
                      {type:'_case', who:'driver_advocate', case: ev.driver_case});
      }
      else if (ev.phase === 'judge'){ setRoster('judge','active'); showTyping('judge'); }
      else if (ev.phase === 'safety_net'){ setRoster('safety_net','active'); showTyping('safety_net'); }
      break;
    case '_case': addCaseCard(ev.who, ev.case); break;
    case 'complaint_received': addComplaint(ev.complaint, ev.trip_id); showTyping('intake'); break;
    case 'rider_message': addRiderMessage(ev.text); break;
    case 'trip_matched': addTripMatched(ev); break;
    case 'trip_unresolved': hideTyping('intake'); setRoster('intake','done'); sealAll(); addTripUnresolved(ev); break;
    // The ticket card (ticket_filed) replaces the triage card; keep the triage for its confidence and reasoning.
    case 'triage_result': lastTriage = ev; break;
    case 'ticket_filed': hideTyping('intake'); setRoster('intake','done'); seal('intake'); addTicket(ev); break;
    case 'agent_start': showTyping(ev.agent); break;
    case 'agent_final': hideTyping(ev.agent); seal(ev.agent); break;
    case 'thinking': hideTyping(ev.agent); addThinking(ev.agent, ev.content); showTyping(ev.agent); break;
    case 'warning': hideTyping(ev.agent); seal(ev.agent); addThinking(ev.agent, ev.content); seal(ev.agent); break;
    case 'tool_call': addToolCall(ev.agent, ev.tool, ev.args); break;
    case 'tool_result': addToolResult(ev.agent, ev.tool, ev.ok, ev.result); break;
    case 'safety_net': hideTyping('safety_net'); setRoster('safety_net','done'); addSafetyNet(ev); break;
    case 'ruling':
      hideAllTyping(); sealAll();
      setRoster('judge','done'); setRoster('safety_net','done');
      addRuling(ev.ruling, ev.elapsed_ms);
      break;
    case 'error': hideAllTyping(); addError(ev); break;
    case 'done': hideAllTyping(); break;
  }
}

/* ---------------------------------------------------------------- paced queue
   Messages are released one at a time so the run reads like a conversation, but the
   total artificial delay is capped (PACE_BUDGET) so the ruling is never held back by
   more than a few seconds. A delay is only ever spent when events are actually backed
   up — with a real LLM backend the stream paces itself and nothing is added. */
const PACE_BUDGET = 2200, PACE_MIN = 160, PACE_MAX = 520;
const WEIGHT = {
  thinking:1, complaint_received:1, triage_result:0, safety_net:1, warning:1, error:1, _case:1,
  trip_matched:1, trip_unresolved:1, ticket_filed:1, rider_message:1,
  phase:0.55, ruling:0.6, tool_call:0.15, tool_result:0, agent_start:0, agent_final:0, done:0,
};
let queue = [], pumping = false, paceLeft = PACE_BUDGET;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const frame = () => new Promise(r => requestAnimationFrame(() => r()));

function enqueue(ev){ queue.push(ev); if (!pumping) pump(); }

async function pump(){
  pumping = true;
  while (queue.length){
    const ev = queue.shift();
    try { render(ev); } catch (e){ console.error('render failed', ev && ev.type, e); }
    const w = WEIGHT[ev.type] != null ? WEIGHT[ev.type] : 0.5;
    let gap = 0;
    if (w > 0 && paceLeft > 0 && queue.length > 0){
      const waiting = queue.reduce((n, e) => n + ((WEIGHT[e.type] != null ? WEIGHT[e.type] : 0.5) >= 0.55 ? 1 : 0), 0);
      const base = Math.max(PACE_MIN, Math.min(PACE_MAX, paceLeft / (waiting + 1)));
      gap = Math.min(paceLeft, base * w);
      paceLeft -= gap;
    }
    // Bookkeeping events (tool results, agent start/final) carry no weight and must not
    // cost a frame each — only what the reader actually sees is allowed to hold the queue.
    if (gap > 0) await sleep(gap);
    else if (w > 0) await frame();
  }
  pumping = false;
}

/* ---------------------------------------------------------------- run control */
function resetUI(){
  queue = []; paceLeft = PACE_BUDGET; complaintShown = false; lastTriage = null;
  bubbleFor = {}; pendingChips = {}; typingEls = {};
  chat.querySelectorAll(':scope > *').forEach(n => { if (n !== typingZone) n.remove(); });
  typingZone.innerHTML = '';
  roster.querySelectorAll('.roster-item').forEach(n => n.classList.remove('active','done'));
  stick = true;
}

function extraQuery(){
  const be = backendSelect.value || '';
  return (be ? `&mode=${encodeURIComponent(be)}` : '') + `&lang=${LANG}`;
}

function openStream(url, btn, busyText, kind){
  btn.disabled = true; btn.textContent = busyText; busy = kind; resetUI();
  const es = new EventSource(url);
  const restore = () => { busy = null; btn.disabled = false; btn.textContent = btn === fileBtn ? T('submit') : T('replay'); };
  es.onmessage = e => {
    let ev; try { ev = JSON.parse(e.data); } catch (err){ console.error('bad event', err); return; }
    ev.agent = ev.agent || ev.role;      // safety-net events carry `role` only
    if (ev.type === 'done'){ es.close(); restore(); }
    enqueue(ev);
  };
  es.onerror = () => { es.close(); restore(); hideAllTyping(); };
  const watcher = setInterval(() => { if (es.readyState === 2){ clearInterval(watcher); restore(); } }, 400);
}

function runFreeform(){
  const text = (complaintInput.value || '').trim(), tripId = tripSel.value || 'auto';
  if (!text){ complaintInput.focus(); return; }
  if (busy) return;
  lastStory = text;
  openStream(`/api/file/stream?trip_id=${encodeURIComponent(tripId)}&complaint=${encodeURIComponent(text)}${extraQuery()}`,
             fileBtn, T('ruling_btn'), 'file');
}
/* The rider picked one of the candidate trips: file the same words against it. */
let lastStory = '';
function resubmitWithTrip(tripId){
  tripSel.value = tripId;
  if (lastStory) complaintInput.value = lastStory;
  growInput();
  runFreeform();
}
function runPreset(){
  const id = sel.value; if (!id) return;
  openStream(`/api/resolve/${id}/stream?${extraQuery().replace(/^&/,'')}`, runBtn, T('replaying'), 'run');
}

/* ---------------------------------------------------------------- embedding API
   The three-pane page (static/three.js) drives the agent room through this object. */
window.RoomUI = {
  I18N, T: k => T(k), esc, conf2, money, fmtTime, typeLabel, toolLabel, rulingLabel, kvList, tagList, bullets, note,
  enqueue: ev => { ev.agent = ev.agent || ev.role; enqueue(ev); },
  reset: () => resetUI(),
  setLang: l => { LANG = l === 'zh' ? 'zh' : 'en'; try { localStorage.setItem('rr_lang', LANG); } catch (e) {} applyStatic(); },
  getLang: () => LANG,
  applyStatic: () => applyStatic(),
};

if (!EMBED){
  /* ---------------------------------------------------------------- wiring */
  document.querySelectorAll('#langToggle button').forEach(b => b.addEventListener('click', () => {
    LANG = b.dataset.lang;
    try { localStorage.setItem('rr_lang', LANG); } catch (e) {}
    applyStatic();
    // Results already on screen stay in the language they were produced in; re-run to see them in the new one.
  }));

  document.querySelectorAll('.chip').forEach(c => c.addEventListener('click', () => {
    complaintInput.value = c.dataset.text;
    growInput(); complaintInput.focus();
  }));

  function growInput(){
    complaintInput.style.height = 'auto';
    complaintInput.style.height = Math.min(140, Math.max(46, complaintInput.scrollHeight)) + 'px';
  }
  complaintInput.addEventListener('input', growInput);
  complaintInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing){ e.preventDefault(); runFreeform(); }
  });
  fileBtn.addEventListener('click', runFreeform);
  runBtn.addEventListener('click', runPreset);

  async function boot(){
    applyStatic();
    try {
      health = await fetch('/api/health').then(r => r.json());
      backendSelect.value = health.llm_mode === 'llm' ? 'llm' : 'deterministic';
      renderBadge();
    }
    catch (e) { modeBadge.textContent = T('badgeFail'); }
    try {
      disputes = (await fetch('/api/disputes').then(r => r.json())).disputes || [];
      trips = (await fetch('/api/trips').then(r => r.json())).trips || [];
    } catch (e) {}
    renderDropdowns();
    sel.disabled = false; runBtn.disabled = false; tripSel.disabled = false; fileBtn.disabled = false;
  }
  boot();
}
