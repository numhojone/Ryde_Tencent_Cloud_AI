/* RydeResolve three-pane demo: Rider app | Agent room | Support console, all on one live case.
   The agent room is the existing group chat (static/app.js, embedded); this file wires the case,
   the rider app and the support console. Every pane subscribes to the case's event stream and
   keeps only the events tagged for it (`pane`: rider | room | human, plus `case` status events). */
(() => {
const R = window.RoomUI;
Object.assign(R.I18N.en, {
  tpTitle:'RydeResolve | Three-pane demo', tpTag:'Rider, agents and support, live on one case',
  tpDemo:'Demo', tpReset:'Reset case', tpFill:'Fill story:',
  tpRider:'Rider', tpRoom:'Agent room', tpHuman:'Support console', tpHelp:'Help with a trip',
  tpRiderEmpty:'Tell us what went wrong with your trip, in your own words.', tpRiderPh:'Type a message', tpSend:'Send',
  tpRoomEmpty:'The agents start working as soon as the rider sends a message.',
  tpNoCases:'No cases need review', tpNoCasesSub:'Cases appear here only when the policy or the safety net needs a person.',
  tpAsk:'Ask about this case', tpAskPh:'e.g. did the driver tell the rider about the route change?',
  tpCheck:'Check wording', tpYouWrote:'You wrote', tpSentAs:'Will be sent as', tpEdit:'Back to edit', tpConfirmAsk:'Confirm and ask',
  tpUnchanged:'Already clear, sent unchanged.', tpChanged:'Spelling, grammar and tone tidied; the meaning is unchanged. You can still edit it.',
  tpApprove:'Approve AI recommendation', tpAdjust:'Adjust amount', tpReject:'Reject claim', tpMore:'Request more information',
  tpAmount:'Refund amount (S$)', tpCancel:'Cancel', tpSubmitDecision:'Submit decision',
  tpNoteOpt:'Note to the rider (optional)', tpNoteReq:'Note to the rider (required)', tpNoteInfo:'What do you need from the rider? (required)',
  tpErrNote:'Please write a note.', tpErrAmt:'Please enter an amount of 0 or more.',
  fillNoShow:'No-show', fillRoute:'Route deviation', fillFare:'Fare dispute', fillDamage:'Damage', fillSafety:'Safety',
  sRyde:'Ryde', sSupport:'Ryde Support', sYou:'You',
  rs:{intake:'Checking your trip', in_review:'In review', resolved_by_ai:'Resolved', with_agent:'With a support agent',
      waiting_for_rider:'Waiting for your reply', resolved_by_human:'Resolved'},
  hs:{intake:'Intake', in_review:'Agents working', resolved_by_ai:'Resolved by AI', with_agent:'Needs review',
      waiting_for_rider:'Waiting for rider reply', resolved_by_human:'Resolved'},
  live:{idle:'Idle', typing:'Typing', working:'Working', waiting:'Waiting for rider', resolved:'Resolved', review:'Needs review',
        online:'Online', answering:'Answering', done:'Done'},
  ocRef:'Reference', ocByAi:'Decided from your trip records', ocByHuman:'Reviewed by a Ryde support agent',
  ocGoodwill:'Goodwill credit', ocNote:'Message from support', ocPolicy:'Policy',
  tripPick:'Choose a trip',
  smWhy:'Why it needs a person', smRec:'AI recommendation', smNoRec:'No AI recommendation: the AI may not rule on safety incidents (policy 5.2).',
  smWho:'Who', smRiderL:'Rider', smDriverL:'Driver', smTrip:'Trip', smClaim:'What the rider claims', smAsks:'Asks for',
  smFacts:'Key facts from the records', smFound:'Evidence found', smMissing:'Missing or thin', smArgs:'Advocates',
  smArgR:'Rider advocate', smArgD:'Driver advocate', smEvidence:'Evidence', smCaseFile:'Safety case file',
  smInterim:'Interim measures (policy 5.3)', smReplies:'Rider replies', smClause:'clause', smNone:'none',
  qaAnswering:'Searching the case record…', qaAnswered:'Answered from the record', qaAsked:'Not in the record: asked the rider',
  qaAfter:'Answered with the rider\'s reply', qaInfo:'Information requested from the rider',
  qaSentRider:'Sent to the rider', qaReply:'Rider replied', qaSources:'Sources', qaYouWrote:'You wrote',
  dbDone:'Decision recorded. The rider has been told.', dbDecided:'Decision', riderSays:'Rider',
  errGeneric:'Something went wrong. Please try again.',
});
Object.assign(R.I18N.zh, {
  tpTitle:'RydeResolve | 三栏演示', tpTag:'乘客、智能体与客服，同一案件实时联动',
  tpDemo:'演示', tpReset:'重置案件', tpFill:'填入示例：',
  tpRider:'乘客', tpRoom:'智能体会话', tpHuman:'客服工作台', tpHelp:'行程求助',
  tpRiderEmpty:'用您自己的话告诉我们这趟行程出了什么问题。', tpRiderPh:'输入消息', tpSend:'发送',
  tpRoomEmpty:'乘客一发出消息，智能体就会开始工作。',
  tpNoCases:'暂无需要审核的案件', tpNoCasesSub:'只有政策或安全网要求人工处理的案件才会出现在这里。',
  tpAsk:'就本案提问', tpAskPh:'例如：司机有没有告诉乘客改道？',
  tpCheck:'检查措辞', tpYouWrote:'您输入的', tpSentAs:'将发送为', tpEdit:'返回修改', tpConfirmAsk:'确认并提问',
  tpUnchanged:'表述已清楚，原样发送。', tpChanged:'已修正拼写、语法和语气，含义不变。仍可修改。',
  tpApprove:'批准 AI 建议', tpAdjust:'调整金额', tpReject:'驳回申诉', tpMore:'请乘客补充信息',
  tpAmount:'退款金额（S$）', tpCancel:'取消', tpSubmitDecision:'提交决定',
  tpNoteOpt:'给乘客的备注（可选）', tpNoteReq:'给乘客的备注（必填）', tpNoteInfo:'需要乘客提供什么？（必填）',
  tpErrNote:'请填写备注。', tpErrAmt:'请输入 0 或以上的金额。',
  fillNoShow:'爽约', fillRoute:'绕路', fillFare:'车费', fillDamage:'清洁费', fillSafety:'安全',
  sRyde:'Ryde', sSupport:'Ryde 客服', sYou:'我',
  rs:{intake:'正在核对行程', in_review:'审核中', resolved_by_ai:'已解决', with_agent:'已转客服专员',
      waiting_for_rider:'等待您的回复', resolved_by_human:'已解决'},
  hs:{intake:'受理中', in_review:'智能体处理中', resolved_by_ai:'AI 已解决', with_agent:'待人工审核',
      waiting_for_rider:'等待乘客回复', resolved_by_human:'已解决'},
  live:{idle:'待命', typing:'输入中', working:'处理中', waiting:'等待乘客', resolved:'已解决', review:'待审核',
        online:'在线', answering:'回答中', done:'完成'},
  ocRef:'参考编号', ocByAi:'依据您的行程记录作出', ocByHuman:'由 Ryde 客服专员审核',
  ocGoodwill:'善意补偿', ocNote:'客服留言', ocPolicy:'政策',
  tripPick:'选择行程',
  smWhy:'为何需要人工', smRec:'AI 建议', smNoRec:'无 AI 建议：安全事件 AI 不得裁决（政策 5.2）。',
  smWho:'当事人', smRiderL:'乘客', smDriverL:'司机', smTrip:'行程', smClaim:'乘客主张', smAsks:'请求',
  smFacts:'记录中的关键事实', smFound:'已有证据', smMissing:'缺失或不足', smArgs:'双方辩护',
  smArgR:'乘客辩护智能体', smArgD:'司机辩护智能体', smEvidence:'证据', smCaseFile:'安全案件材料',
  smInterim:'临时措施（政策 5.3）', smReplies:'乘客回复', smClause:'条款', smNone:'无',
  qaAnswering:'正在检索案件记录…', qaAnswered:'已根据记录回答', qaAsked:'记录中没有：已询问乘客',
  qaAfter:'已结合乘客回复回答', qaInfo:'已请乘客补充信息',
  qaSentRider:'已发送给乘客', qaReply:'乘客回复', qaSources:'来源', qaYouWrote:'您输入的',
  dbDone:'决定已记录，并已通知乘客。', dbDecided:'决定', riderSays:'乘客',
  errGeneric:'出错了，请重试。',
});
const T = R.T, CUR = 'S$';
const $ = id => document.getElementById(id);
const mk = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const money = v => (typeof v === 'number' && isFinite(v)) ? CUR + v.toFixed(2) : String(v);

const FILLS = {
  en: [
    ['fillNoShow', 'I waited at Tiong Bahru Plaza but the driver never came, and I was still charged a $5 cancellation fee.'],
    ['fillRoute', 'The driver took a much longer route from Orchard Central to Changi Airport T3. The fare was $35 when I usually pay $28, and he never told me about any change.'],
    ['fillFare', 'The fare was $16.50 but the upfront quote at Bugis Junction was $12.00. Nobody told me the price had gone up.'],
    ['fillDamage', 'I was charged a S$35 cleaning fee after my ride from Orchard MRT, but I never spilled anything.'],
    ['fillSafety', 'The driver was speeding over 100 km/h and shouted at me when I asked him to slow down. I felt really unsafe.'],
  ],
  zh: [
    ['fillNoShow', '我在中峇鲁广场等了很久，司机一直没来，还被收了$5取消费。'],
    ['fillRoute', '司机从Orchard Central到樟宜机场绕了一大圈，多收了我不少钱，也没有告诉我为什么改道。'],
    ['fillFare', '在白沙浮广场上车时报价是$12.00，最后收了$16.50，没有人告诉我涨价。'],
    ['fillDamage', '从乌节地铁站坐车后被收了S$35清洁费，但我根本没有弄脏车。'],
    ['fillSafety', '司机开到100 km/h以上严重超速，我让他开慢点他还吼我，我觉得很不安全。'],
  ],
};

let health = null, caseId = null, status = null, streams = [], summary = null, qa = {}, riderBusy = false;
let roomWorking = false, askBusy = false, decisionAction = null;

/* ---------------------------------------------------------------- live status indicators */
function setLive(pane, key, tone){
  const n = $('st-' + pane); if (!n) return;
  n.dataset.tone = tone || key;
  n.querySelector('span').textContent = (T('live') || {})[key] || key;
}
function refreshLive(){
  const inp = $('riderInput');
  if (document.activeElement === inp && inp.value.trim()) setLive('rider', 'typing');
  else if (status === 'waiting_for_rider') setLive('rider', 'waiting', 'attn');
  else if (status === 'resolved_by_ai' || status === 'resolved_by_human') setLive('rider', 'resolved', 'ok');
  else setLive('rider', 'online', 'idle');

  if (roomWorking) setLive('room', 'working', 'busy');
  else if (caseId && status !== 'intake') setLive('room', 'done', 'ok');
  else setLive('room', 'idle');

  if (askBusy) setLive('human', 'answering', 'busy');
  else if (status === 'with_agent') setLive('human', 'review', 'attn');
  else if (status === 'waiting_for_rider') setLive('human', 'waiting', 'busy');
  else if (status === 'resolved_by_human') setLive('human', 'resolved', 'ok');
  else setLive('human', 'idle');
}

/* ---------------------------------------------------------------- mobile tabs */
function showPane(name){
  document.querySelectorAll('#tabs button').forEach(b => {
    const on = b.dataset.pane === name;
    b.classList.toggle('on', on); b.setAttribute('aria-selected', on ? 'true' : 'false');
    if (on) b.classList.remove('ping');
  });
  document.querySelectorAll('.pane').forEach(p => p.classList.toggle('on', p.dataset.pane === name));
}
function ping(name){
  const b = document.querySelector(`#tabs button[data-pane="${name}"]`);
  if (b && !b.classList.contains('on')) b.classList.add('ping');
}
document.querySelectorAll('#tabs button').forEach(b => b.addEventListener('click', () => showPane(b.dataset.pane)));

/* ---------------------------------------------------------------- API */
async function api(path, body){
  const r = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  let data = null; try { data = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((data && data.detail) || T('errGeneric'));
  return data;
}

/* ---------------------------------------------------------------- streams */
function subscribe(id){
  closeStreams();
  ['rider', 'room', 'human'].forEach(pane => {
    const es = new EventSource(`/api/cases/${encodeURIComponent(id)}/events`);
    es.onmessage = e => {
      let ev; try { ev = JSON.parse(e.data); } catch (err){ return; }
      if (ev.case_id !== caseId) return;
      if (ev.pane === 'case'){ if (pane === 'rider') onStatus(ev); return; }   // status: handled once
      if (ev.pane !== pane) return;
      ({rider: onRider, room: onRoom, human: onHuman})[pane](ev);
      ping(pane);
    };
    streams.push(es);
  });
}
function closeStreams(){ streams.forEach(s => s.close()); streams = []; }

function onStatus(ev){
  status = ev.status;
  if (ev.status === 'intake' || ev.status === 'in_review') roomWorking = true;
  const bar = $('ticketBar');
  if (ev.reference && ev.reference.startsWith('DISP-')){ bar.hidden = false; $('tbRef').textContent = ev.reference; }
  $('tbStatus').textContent = (T('rs') || {})[ev.status] || ev.status;
  $('tbStatus').dataset.s = ev.status;
  riderTyping(ev.status === 'intake' || ev.status === 'in_review');
  if (summary) renderSummary();
  syncDecisionBar();
  refreshLive();
}

/* ---------------------------------------------------------------- LEFT: rider app */
const riderChat = $('riderChat');
function riderScroll(){ riderChat.scrollTop = riderChat.scrollHeight; }
function riderRow(side, sender, cls){
  $('riderEmpty').hidden = true;
  const row = mk('div', `rm ${side}` + (cls ? ' ' + cls : ''));
  if (sender) row.appendChild(mk('div', 'rm-who', sender));
  const b = mk('div', 'rm-bubble'); row.appendChild(b);
  riderChat.insertBefore(row, $('riderTyping') || null);
  return b;
}
function riderTyping(on){
  let t = $('riderTyping');
  if (on && !t){
    t = mk('div', 'rm left rm-typing'); t.id = 'riderTyping';
    t.innerHTML = '<div class="rm-bubble"><span class="dots"><i></i><i></i><i></i></span></div>';
    riderChat.appendChild(t);
  } else if (!on && t) t.remove();
  riderScroll();
}
function onRider(ev){
  switch (ev.type){
    case 'rider_message': riderRow('right', null, 'me').textContent = ev.text; break;
    case 'assistant_message': riderRow('left', T('sRyde')).textContent = ev.text; break;
    case 'support_message': riderRow('left', T('sSupport'), 'support').textContent = ev.text; break;
    case 'trip_choice': {
      const b = riderRow('left', T('sRyde'));
      b.appendChild(mk('p', null, ev.text));
      const list = mk('div', 'rm-trips');
      (ev.candidates || []).forEach(c => {
        const btn = mk('button', 'rm-trip', c.label); btn.type = 'button';
        btn.addEventListener('click', () => sendRider(c.label, c.trip_id));
        list.appendChild(btn);
      });
      b.appendChild(list);
      break;
    }
    case 'ticket_update': break;            // the ticket bar follows the case status
    case 'handoff': { const b = riderRow('left', T('sRyde'), 'handoff'); b.textContent = ev.text; break; }
    case 'outcome': riderOutcome(ev.card); break;
  }
  riderScroll();
}
function riderOutcome(c){
  const b = riderRow('left', c.decided_by === 'human' ? T('sSupport') : T('sRyde'), 'outcome ' + c.decision);
  b.appendChild(mk('div', 'oc-title', c.title));
  if (c.refund_amount != null) b.appendChild(mk('div', 'oc-amount', money(c.refund_amount)));
  if (c.goodwill_credit) b.appendChild(mk('div', 'oc-extra', `${T('ocGoodwill')}: ${money(c.goodwill_credit)}`));
  b.appendChild(mk('p', 'oc-reason', c.reason));
  if (c.note){ const n = mk('div', 'oc-note'); n.appendChild(mk('span', 'oc-k', T('ocNote'))); n.appendChild(mk('span', null, c.note)); b.appendChild(n); }
  const foot = mk('div', 'oc-foot');
  if (c.policy_section) foot.appendChild(mk('span', null, c.policy_section));
  foot.appendChild(mk('span', null, `${T('ocRef')} ${c.reference}`));
  foot.appendChild(mk('span', null, c.decided_by === 'human' ? T('ocByHuman') : T('ocByAi')));
  b.appendChild(foot);
}

async function sendRider(text, tripId){
  text = (text || '').trim();
  if ((!text && !tripId) || riderBusy) return;
  if (caseId && (status === 'resolved_by_ai' || status === 'resolved_by_human')) resetCase();
  riderBusy = true; $('riderSend').disabled = true;
  try {
    if (!caseId){
      showPane('rider');
      const snap = await api('/api/cases', {story: text, mode: $('modeSelect').value, lang: R.getLang()});
      caseId = snap.id; status = snap.status; roomWorking = true;
      R.reset(); $('chat').querySelectorAll('.empty-state').forEach(n => n.remove());
      subscribe(caseId);
    } else {
      await api(`/api/cases/${caseId}/rider-message`, {text, trip_id: tripId || null});
      if (tripId) roomWorking = true;
    }
    $('riderInput').value = ''; growRider();
  } catch (e){
    riderRow('left', T('sRyde'), 'error').textContent = e.message;
  } finally {
    riderBusy = false; $('riderSend').disabled = false; refreshLive();      // never leave Send stuck
  }
}
window.RR_PICK_TRIP = (tripId, label) => sendRider(label, tripId);

function growRider(){ const i = $('riderInput'); i.style.height = 'auto'; i.style.height = Math.min(120, Math.max(42, i.scrollHeight)) + 'px'; }
$('riderInput').addEventListener('input', () => { growRider(); refreshLive(); });
$('riderInput').addEventListener('blur', refreshLive);
$('riderInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing){ e.preventDefault(); sendRider($('riderInput').value); }
});
$('riderForm').addEventListener('submit', e => { e.preventDefault(); sendRider($('riderInput').value); });

/* ---------------------------------------------------------------- MIDDLE: agent room */
function onRoom(ev){
  R.enqueue(ev);
  if (ev.type === 'done' || ev.type === 'error'){ roomWorking = false; refreshLive(); }
}

/* ---------------------------------------------------------------- RIGHT: support console */
function onHuman(ev){
  if (ev.type === 'case_escalated' || ev.type === 'summary'){ summary = ev.summary; renderSummary(); showConsole(); }
  else if (ev.type === 'qa'){ qa[ev.entry.id] = ev.entry; renderQA(); }
  else if (ev.type === 'rider_message'){ qa['r' + ev.seq] = {id: 'r' + ev.seq, kind: 'rider', text: ev.text, at: ev.at}; renderQA(); }
  else if (ev.type === 'decision'){ renderDecided(ev.decision); }
  syncDecisionBar(); refreshLive();
}
function showConsole(){ $('consoleIdle').hidden = true; $('consoleCase').hidden = false; }

function block(title, node, cls){
  const s = mk('div', 'sm-block' + (cls ? ' ' + cls : ''));
  s.appendChild(mk('h4', null, title)); if (node) s.appendChild(node); return s;
}
function evidenceChips(ev){
  const wrap = mk('div', 'evidence');
  const chips = mk('div', 'ev-chips'); wrap.appendChild(chips);
  Object.keys(ev || {}).forEach(tool => {
    const chip = mk('button', 'ev-chip'); chip.type = 'button'; chip.dataset.state = 'ok'; chip.setAttribute('aria-expanded', 'false');
    chip.appendChild(mk('span', 'st')); chip.appendChild(mk('span', 'lb', R.toolLabel(tool)));
    chip.addEventListener('click', () => {
      const open = chip.getAttribute('aria-expanded') === 'true';
      wrap.querySelectorAll('.ev-chip').forEach(c => c.setAttribute('aria-expanded', 'false'));
      const old = wrap.querySelector('.ev-panel'); if (old) old.remove();
      if (open) return;
      chip.setAttribute('aria-expanded', 'true');
      const p = mk('div', 'ev-panel'); const row = mk('div', 'ep-row');
      row.appendChild(mk('span', 'ep-k', tool)); row.appendChild(mk('pre', null, JSON.stringify(ev[tool], null, 2)));
      p.appendChild(row); wrap.appendChild(p);
    });
    chips.appendChild(chip);
  });
  return wrap;
}
function renderSummary(){
  const s = summary; if (!s) return;
  const box = $('summary'); box.innerHTML = '';
  const card = mk('article', 'sm-card');
  const top = mk('div', 'sm-top');
  top.appendChild(mk('span', 'sm-ref', s.reference));
  if (s.category && s.category.label) top.appendChild(mk('span', 'tag rose', s.category.label));
  top.appendChild(mk('span', 'sm-status', (T('hs') || {})[status] || status));
  card.appendChild(top);

  const why = block(T('smWhy'), R.bullets(s.escalation_reasons || []), 'why');
  card.appendChild(why);
  const rec = s.recommendation;
  const recNode = rec
    ? mk('div', 'sm-rec', `${R.rulingLabel(rec.ruling)}${rec.refund_amount != null ? ' · ' + money(rec.refund_amount) : ''}${rec.goodwill_credit ? ' · +' + money(rec.goodwill_credit) : ''}`)
    : mk('p', 'note', T('smNoRec'));
  card.appendChild(block(T('smRec'), recNode, 'rec'));

  const route = s.trip ? `${s.trip.id} · ${s.trip.route}${s.trip.time ? ' · ' + R.fmtTime(s.trip.time) : ''}` : '-';
  card.appendChild(block(T('smWho'), R.kvList([
    [T('smRiderL'), `${s.who.rider.id || '-'}${s.who.rider.line ? ' · ' + s.who.rider.line : ''}`],
    [T('smDriverL'), `${s.who.driver.id || '-'}${s.who.driver.line ? ' · ' + s.who.driver.line : ''}`],
    [T('smTrip'), route],
  ])));
  const claim = mk('div');
  claim.appendChild(mk('blockquote', 'sm-quote', s.claim.story || ''));
  if (s.claim.requested_amount != null || s.claim.requested_resolution)
    claim.appendChild(mk('p', 'note', `${T('smAsks')}: ${s.claim.requested_amount != null ? money(s.claim.requested_amount) + ' · ' : ''}${s.claim.requested_resolution || ''}`));
  card.appendChild(block(T('smClaim'), claim));
  if ((s.key_facts || []).length) card.appendChild(block(T('smFacts'), R.bullets(s.key_facts, 'check')));

  const ev = mk('div');
  const row = mk('div', 'sm-ev');
  row.appendChild(mk('span', 'sm-k', T('smFound'))); row.appendChild(R.tagList(s.evidence_found.length ? s.evidence_found : [T('smNone')], 'blue'));
  ev.appendChild(row);
  const row2 = mk('div', 'sm-ev');
  row2.appendChild(mk('span', 'sm-k', T('smMissing'))); row2.appendChild(R.tagList(s.evidence_missing.length ? s.evidence_missing : [T('smNone')], 'rose'));
  ev.appendChild(row2);
  if (s.evidence) ev.appendChild(evidenceChips(s.evidence));
  card.appendChild(block(T('smEvidence'), ev));

  if (s.advocates && (s.advocates.rider || s.advocates.driver))
    card.appendChild(block(T('smArgs'), R.kvList([[T('smArgR'), s.advocates.rider || '-'], [T('smArgD'), s.advocates.driver || '-']])));
  if (s.case_file){
    const cf = mk('div');
    cf.appendChild(R.bullets(s.case_file.facts || []));
    cf.appendChild(mk('h5', null, T('smInterim')));
    cf.appendChild(R.bullets(s.case_file.interim_measures || []));
    card.appendChild(block(T('smCaseFile'), cf, 'safety'));
  }
  if ((s.rider_replies || []).length)
    card.appendChild(block(T('smReplies'), R.bullets(s.rider_replies.map(m => `${R.fmtTime(m.at)} · ${m.text}`))));
  box.appendChild(card);
}

function renderQA(){
  const th = $('qaThread'); th.innerHTML = '';
  Object.values(qa).forEach(e => {
    if (e.kind === 'rider'){
      const d = mk('div', 'qa-item rider');
      d.appendChild(mk('div', 'qa-q', `${T('riderSays')}: ${e.text}`));
      th.appendChild(d); return;
    }
    const d = mk('div', 'qa-item ' + (e.status || ''));
    d.appendChild(mk('div', 'qa-q', e.question));
    if (e.original && e.original !== e.question) d.appendChild(mk('div', 'qa-orig', `${T('qaYouWrote')}: ${e.original}`));
    const st = {answering:'qaAnswering', answered:'qaAnswered', asked_rider: e.kind === 'info_request' ? 'qaInfo' : 'qaAsked', answered_after_reply:'qaAfter'}[e.status];
    if (st) d.appendChild(mk('span', 'qa-status', T(st)));
    if (e.answer) d.appendChild(mk('div', 'qa-a', e.answer));
    if ((e.citations || []).length){
      const c = mk('div', 'qa-cites'); c.appendChild(mk('span', 'sm-k', T('qaSources')));
      c.appendChild(R.tagList([...new Set(e.citations)], 'blue')); d.appendChild(c);
    }
    if (e.sent_to_rider) d.appendChild(mk('div', 'qa-sent', `${T('qaSentRider')}: ${e.sent_to_rider}`));
    if (e.reply) d.appendChild(mk('div', 'qa-reply', `${T('qaReply')}: ${e.reply.text}`));
    th.appendChild(d);
  });
  const sc = $('consoleScroll'); sc.scrollTop = sc.scrollHeight;
}

/* ask: rephrase first, the human confirms or edits, then the case-QA agent answers */
$('askForm').addEventListener('submit', async e => {
  e.preventDefault();
  const text = $('askInput').value.trim(); if (!text || !caseId || askBusy) return;
  askBusy = true; $('askBtn').disabled = true; refreshLive();
  try {
    const r = await api(`/api/cases/${caseId}/human/rephrase`, {text, purpose: 'qa'});
    $('qcOrig').textContent = r.original; $('qcEdit').value = r.rephrased;
    $('qcNote').textContent = r.changed ? T('tpChanged') : T('tpUnchanged');
    $('askForm').hidden = true; $('askConfirm').hidden = false; $('qcEdit').focus();
  } catch (err){ $('qcNote').textContent = err.message; }
  finally { askBusy = false; syncDecisionBar(); refreshLive(); }
});
$('qcCancel').addEventListener('click', () => { $('askConfirm').hidden = true; $('askForm').hidden = false; $('askInput').focus(); });
$('qcSend').addEventListener('click', async () => {
  const q = $('qcEdit').value.trim(); if (!q || askBusy) return;
  askBusy = true; $('qcSend').disabled = true; refreshLive();
  try {
    await api(`/api/cases/${caseId}/human/ask`, {question: q, original: $('qcOrig').textContent});
    $('askInput').value = ''; $('askConfirm').hidden = true; $('askForm').hidden = false;
  } catch (err){ $('qcNote').textContent = err.message; }
  finally { askBusy = false; $('qcSend').disabled = false; syncDecisionBar(); refreshLive(); }
});

/* decision bar */
function syncDecisionBar(){
  const bar = $('decisionBar');
  const open = status === 'with_agent' || status === 'waiting_for_rider';
  bar.hidden = !(summary && (open || status === 'resolved_by_human'));
  bar.querySelectorAll('.db-buttons button').forEach(b => { b.disabled = !open; });
  bar.querySelector('.db-buttons').hidden = status === 'resolved_by_human';
  $('dbApprove').disabled = !open || !(summary && summary.recommendation);
  $('askBtn').disabled = !open || askBusy;
  $('askInput').disabled = !open;
}
document.querySelectorAll('.db-buttons button').forEach(b => b.addEventListener('click', () => openDecision(b.dataset.act)));
function openDecision(act){
  decisionAction = act;
  document.querySelectorAll('.db-buttons button').forEach(b => b.classList.toggle('sel', b.dataset.act === act));
  $('dbForm').hidden = false; $('dbErr').textContent = '';
  $('dbAmtWrap').hidden = act !== 'adjust';
  if (act === 'adjust' && summary && summary.recommendation && summary.recommendation.refund_amount != null)
    $('dbAmount').value = summary.recommendation.refund_amount;
  $('dbNoteLbl').textContent = act === 'request_info' ? T('tpNoteInfo') : (act === 'adjust' ? T('tpNoteReq') : T('tpNoteOpt'));
  $('dbNote').focus();
}
$('dbCancel').addEventListener('click', () => { $('dbForm').hidden = true; decisionAction = null;
  document.querySelectorAll('.db-buttons button').forEach(b => b.classList.remove('sel')); });
$('dbSubmit').addEventListener('click', async () => {
  const note = $('dbNote').value.trim(), act = decisionAction;
  if (!act) return;
  const amt = $('dbAmount').value === '' ? null : Number($('dbAmount').value);
  if ((act === 'adjust' || act === 'request_info') && !note){ $('dbErr').textContent = T('tpErrNote'); return; }
  if (act === 'adjust' && (amt == null || !isFinite(amt) || amt < 0)){ $('dbErr').textContent = T('tpErrAmt'); return; }
  $('dbSubmit').disabled = true;
  try {
    await api(`/api/cases/${caseId}/human/decision`, {action: act, amount: amt, note});
    $('dbNote').value = ''; $('dbForm').hidden = true;
    document.querySelectorAll('.db-buttons button').forEach(b => b.classList.remove('sel'));
  } catch (err){ $('dbErr').textContent = err.message; }
  finally { $('dbSubmit').disabled = false; }
});
function renderDecided(d){
  const bar = $('decisionBar');
  let done = bar.querySelector('.db-done');
  if (!done){ done = mk('div', 'db-done'); bar.prepend(done); }
  const amount = d.amount != null ? ' · ' + money(d.amount) : '';
  done.textContent = `${T('dbDecided')}: ${(T(({approve:'tpApprove', adjust:'tpAdjust', reject:'tpReject'})[d.action]) || d.action)}${amount}. ${T('dbDone')}`;
}

/* ---------------------------------------------------------------- demo strip */
function renderFills(){
  const box = $('fills'); box.innerHTML = '';
  (FILLS[R.getLang()] || FILLS.en).forEach(([k, text]) => {
    const b = mk('button', 'chip', T(k)); b.type = 'button';
    b.addEventListener('click', () => { const i = $('riderInput'); i.value = text; growRider(); i.focus(); showPane('rider'); refreshLive(); });
    box.appendChild(b);
  });
}
function resetCase(){
  closeStreams();
  caseId = null; status = null; summary = null; qa = {}; roomWorking = false; askBusy = false; decisionAction = null;
  riderChat.querySelectorAll('.rm').forEach(n => n.remove());
  $('riderEmpty').hidden = false; $('ticketBar').hidden = true;
  R.reset();
  const es = mk('div', 'empty-state', T('tpRoomEmpty')); es.dataset.i18n = 'tpRoomEmpty';
  $('chat').insertBefore(es, $('typingZone'));
  $('summary').innerHTML = ''; $('qaThread').innerHTML = '';
  $('consoleIdle').hidden = false; $('consoleCase').hidden = true;
  $('askConfirm').hidden = true; $('askForm').hidden = false; $('dbForm').hidden = true;
  const done = $('decisionBar').querySelector('.db-done'); if (done) done.remove();
  syncDecisionBar(); refreshLive();
}
$('resetBtn').addEventListener('click', resetCase);
$('langSelect').addEventListener('change', e => {
  R.setLang(e.target.value); renderFills(); refreshLive();
  if (status) $('tbStatus').textContent = (T('rs') || {})[status] || status;
  renderSummary(); renderQA();
});

async function boot(){
  $('langSelect').value = R.getLang();
  R.applyStatic(); renderFills(); refreshLive(); syncDecisionBar();
  try {
    health = await api('/api/health');
    const llmOpt = $('modeSelect').querySelector('option[value="llm"]');
    if (!health.has_api_key){ llmOpt.disabled = true; $('modeSelect').value = 'deterministic'; }
    else $('modeSelect').value = health.llm_mode === 'llm' ? 'llm' : 'deterministic';
  } catch (e) { $('modeSelect').value = 'deterministic'; }
}
boot();
})();
