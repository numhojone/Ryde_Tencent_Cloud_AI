/* RydeResolve three-pane demo: Rider app | Agent room | Support console.
   Who is using the page comes from the server session (demo login): a rider, or the support agent.

   Rider:   stage 1  describe the problem and confirm the trip (left pane only; nothing else runs)
            stage 2  the case runs: the story and trip go to the agent room
            stage 3  the outcome, or "passed to a support agent", plus questions from support
   Support: a queue of cases that were handed to a person (any rider); opening one fills all three panes,
            the rider's conversation read-only on the left.

   The agent room is the existing group chat (static/app.js, embedded). Every pane subscribes to the case's
   event stream and keeps only the events tagged for it (`pane`: rider | room | human, plus `case` status). */
(() => {
const R = window.RoomUI;
Object.assign(R.I18N.en, {
  tpTitle:'Ryde Support | Three-pane demo', tpTag:'Rider, agents and support, live on one case',
  tpDemo:'Demo', tpReset:'Reset case', tpFill:'Fill story:',
  tpRider:'Rider', tpRoom:'Agent room', tpHuman:'Support console', tpHelp:'Help with a trip',
  tpRiderEmpty:'Tell us what happened.', tpRiderPh:'Type a message', tpSend:'Send',
  tpRoomEmpty:'Waiting for a case. The agents start once the rider confirms which trip it is about.',
  tpNoCases:'No cases need review', tpNoCasesSub:'Cases appear here only when the policy or the safety net needs a person.',
  tpAsk:'Ask about this case', tpAskPh:'e.g. did the driver tell the rider about the route change?',
  tpCheck:'Check wording', tpYouWrote:'You wrote', tpSentAs:'Will be sent as', tpEdit:'Back to edit', tpConfirmAsk:'Confirm and ask',
  tpUnchanged:'Already clear, sent unchanged.', tpChanged:'Spelling, grammar and tone tidied; the meaning is unchanged. You can still edit it.',
  tpApprove:'Approve AI recommendation', tpAdjust:'Adjust amount', tpReject:'Reject claim', tpMore:'Request more information',
  tpAmount:'Refund amount (S$)', tpCancel:'Cancel', tpSubmitDecision:'Submit decision',
  tpNoteOpt:'Note to the rider (optional)', tpNoteReq:'Note to the rider (required)', tpNoteInfo:'What do you need from the rider? (required)',
  tpErrNote:'Please write a note.', tpErrAmt:'Please enter an amount of 0 or more.',
  tpSignOut:'Sign out',
  tpQueue:'Your cases for review', tpOpen:'Open', tpOpened:'Open now',
  sRyde:'Ryde', sSupport:'Ryde Support', sYou:'You',
  hello:n => `Hi ${n}. Tell us what happened.`, finding:'Finding your trip…',
  isThis:'Is this the one?', yes:'Yes, this one', noOther:'No, pick another', pickOne:'Choose this trip',
  chose:t => `That one: ${t}`, otherTrips:'Your recent trips:', whyMatch:'Why it might match',
  st_completed:'completed', st_cancelled:'cancelled', feeOf:m => `${m} fee charged`,
  rs:{intake:'Checking your trip', in_review:'In review', resolved_by_ai:'Resolved', with_agent:'With a support agent',
      waiting_for_rider:'Waiting for your reply', waiting_for_driver:'With a support agent', waiting_for_both:'Waiting for your reply',
      resolved_by_human:'Resolved'},
  hs:{intake:'Intake', in_review:'Agents working', resolved_by_ai:'Resolved by AI', with_agent:'Needs review',
      waiting_for_rider:'Waiting for rider reply', waiting_for_driver:'Waiting for driver reply',
      waiting_for_both:'Waiting for rider and driver', resolved_by_human:'Resolved'},
  live:{idle:'Idle', typing:'Typing', working:'Working', waiting:'Waiting for rider', resolved:'Resolved', review:'Needs review',
        online:'Online', answering:'Answering', done:'Done', finding:'Finding trip', readonly:'Read-only',
        replyNeeded:'Reply needed', waitingDriver:'Waiting for driver', waitingBoth:'Waiting for rider and driver'},
  ocRef:'Reference', ocByAi:'Decided from your trip records', ocByHuman:'Reviewed by a Ryde support agent',
  ocGoodwill:'Goodwill credit', ocNote:'Message from support',
  smWhy:'Why it needs a person', smRec:'AI recommendation', smNoRec:'No AI recommendation: the AI may not rule on safety incidents (policy 5.2).',
  smWho:'Who', smRiderL:'Rider', smDriverL:'Driver', smTrip:'Trip', smClaim:'What the rider claims', smAsks:'Asks for',
  smFacts:'Key facts from the records', smFound:'Evidence found', smMissing:'Missing or thin', smArgs:'Advocates',
  smArgR:'Rider advocate', smArgD:'Driver advocate', smEvidence:'Evidence', smCaseFile:'Safety case file',
  smInterim:'Interim measures (policy 5.3)', smReplies:'Rider replies', smNone:'none',
  qaAnswering:'Searching the case record…', qaAnswered:'Answered from the record', qaAsked:'Not in the record: asked the rider',
  qaAfter:'Answered with the rider\'s reply', qaInfo:'Information requested from the rider',
  qaSentRider:'Sent to the rider', qaReply:'Rider replied', qaSources:'Sources', qaYouWrote:'You wrote',
  dbDone:'Decision recorded. The rider has been told.', dbDecided:'Decision', riderSays:'Rider',
  errGeneric:'Something went wrong. Please try again.',
  tpDriver:'Driver', tgTitle:'View as', drvHelp:'Driver inbox',
  drvIntro:'You will only see questions from Ryde Support here.', drvEmpty:'No questions from Ryde Support right now.', drvPh:'Reply to Ryde Support',
  drvNoPending:'There is no question waiting for a reply.', drvRider:n => `Rider: ${n}`, drvAck:'Thanks. Your reply has been sent to Ryde Support.',
  askTo:'If the record has no answer, ask', askToShort:'Ask', askAuto:'Auto', askRider:'Rider', askDriver:'Driver',
  willReceive:p => `The ${p} will receive`, toRider:'To rider', toDriver:'To driver', fromRecord:'From the record',
  qaSent:'Sent', qaAnsweredLbl:'Answered', driverReplied:'Driver replied', riderReplied:'Rider replied',
  driverPending:'A driver reply is still pending.', riderPending:'A rider reply is still pending.',
  smDriverReplies:'Driver replies',
  catRoute:'Route', catNoShow:'Cancellation fee', catDamage:'Cleaning or damage fee', catSafety:'Safety',
  tpSignedInAs:d => `Signed in as ${d}`, drvDriver:d => `Driver: ${d}`,
  drvNoCaseMsg:'The driver view shows the driver of your active case once a case is open.',
  mismatch:(t, s) => `The ticket for this ride is a ${t}, but your story sounds like a ${s}. Continue with this ride as a ${t}?`,
  mmYes:t => `Yes, continue as ${t}`, existingCase:r => `This ride already has a case (${r}). Opening it.`,
  tpRiderConsole:'Your cases that need a person appear here. In this demo the console works on your own cases only.',
});
Object.assign(R.I18N.zh, {
  tpTitle:'Ryde 客服 | 三栏演示', tpTag:'乘客、智能体与客服，同一案件实时联动',
  tpDemo:'演示', tpReset:'重置案件', tpFill:'填入示例：',
  tpRider:'乘客', tpRoom:'智能体会话', tpHuman:'客服工作台', tpHelp:'行程求助',
  tpRiderEmpty:'告诉我们发生了什么。', tpRiderPh:'输入消息', tpSend:'发送',
  tpRoomEmpty:'等待案件。乘客确认是哪一趟行程后，智能体才会开始工作。',
  tpNoCases:'暂无需要审核的案件', tpNoCasesSub:'只有政策或安全网要求人工处理的案件才会出现在这里。',
  tpAsk:'就本案提问', tpAskPh:'例如：司机有没有告诉乘客改道？',
  tpCheck:'检查措辞', tpYouWrote:'您输入的', tpSentAs:'将发送为', tpEdit:'返回修改', tpConfirmAsk:'确认并提问',
  tpUnchanged:'表述已清楚，原样发送。', tpChanged:'已修正拼写、语法和语气，含义不变。仍可修改。',
  tpApprove:'批准 AI 建议', tpAdjust:'调整金额', tpReject:'驳回申诉', tpMore:'请乘客补充信息',
  tpAmount:'退款金额（S$）', tpCancel:'取消', tpSubmitDecision:'提交决定',
  tpNoteOpt:'给乘客的备注（可选）', tpNoteReq:'给乘客的备注（必填）', tpNoteInfo:'需要乘客提供什么？（必填）',
  tpErrNote:'请填写备注。', tpErrAmt:'请输入 0 或以上的金额。',
  tpSignOut:'退出登录',
  tpQueue:'您的待审核案件', tpOpen:'打开', tpOpened:'正在查看',
  sRyde:'Ryde', sSupport:'Ryde 客服', sYou:'我',
  hello:n => `${n}，您好。请告诉我们发生了什么。`, finding:'正在查找您的行程…',
  isThis:'是这一趟吗？', yes:'是，就是这趟', noOther:'不是，选其他行程', pickOne:'选择这趟行程',
  chose:t => `是这一趟：${t}`, otherTrips:'您最近的行程：', whyMatch:'可能符合的原因',
  st_completed:'已完成', st_cancelled:'已取消', feeOf:m => `已收费 ${m}`,
  rs:{intake:'正在核对行程', in_review:'审核中', resolved_by_ai:'已解决', with_agent:'已转客服专员',
      waiting_for_rider:'等待您的回复', waiting_for_driver:'已转客服专员', waiting_for_both:'等待您的回复', resolved_by_human:'已解决'},
  hs:{intake:'受理中', in_review:'智能体处理中', resolved_by_ai:'AI 已解决', with_agent:'待人工审核',
      waiting_for_rider:'等待乘客回复', waiting_for_driver:'等待司机回复', waiting_for_both:'等待乘客和司机回复', resolved_by_human:'已解决'},
  live:{idle:'待命', typing:'输入中', working:'处理中', waiting:'等待乘客', resolved:'已解决', review:'待审核',
        online:'在线', answering:'回答中', done:'完成', finding:'查找行程', readonly:'只读',
        replyNeeded:'待回复', waitingDriver:'等待司机', waitingBoth:'等待乘客和司机'},
  ocRef:'参考编号', ocByAi:'依据您的行程记录作出', ocByHuman:'由 Ryde 客服专员审核',
  ocGoodwill:'善意补偿', ocNote:'客服留言',
  smWhy:'为何需要人工', smRec:'AI 建议', smNoRec:'无 AI 建议：安全事件 AI 不得裁决（政策 5.2）。',
  smWho:'当事人', smRiderL:'乘客', smDriverL:'司机', smTrip:'行程', smClaim:'乘客主张', smAsks:'请求',
  smFacts:'记录中的关键事实', smFound:'已有证据', smMissing:'缺失或不足', smArgs:'双方辩护',
  smArgR:'乘客辩护智能体', smArgD:'司机辩护智能体', smEvidence:'证据', smCaseFile:'安全案件材料',
  smInterim:'临时措施（政策 5.3）', smReplies:'乘客回复', smNone:'无',
  qaAnswering:'正在检索案件记录…', qaAnswered:'已根据记录回答', qaAsked:'记录中没有：已询问乘客',
  qaAfter:'已结合乘客回复回答', qaInfo:'已请乘客补充信息',
  qaSentRider:'已发送给乘客', qaReply:'乘客回复', qaSources:'来源', qaYouWrote:'您输入的',
  dbDone:'决定已记录，并已通知乘客。', dbDecided:'决定', riderSays:'乘客',
  errGeneric:'出错了，请重试。',
  tpDriver:'司机', tgTitle:'查看身份', drvHelp:'司机消息',
  drvIntro:'这里只会显示 Ryde 客服向您提出的问题。', drvEmpty:'目前没有来自 Ryde 客服的问题。', drvPh:'回复 Ryde 客服',
  drvNoPending:'目前没有待回复的问题。', drvRider:n => `乘客：${n}`, drvAck:'谢谢，您的回复已发送给 Ryde 客服。',
  askTo:'若记录中没有答案，询问', askToShort:'询问', askAuto:'自动', askRider:'乘客', askDriver:'司机',
  willReceive:p => `${p === 'driver' ? '司机' : '乘客'}将收到`, toRider:'发给乘客', toDriver:'发给司机', fromRecord:'来自记录',
  qaSent:'已发送', qaAnsweredLbl:'已回答', driverReplied:'司机回复', riderReplied:'乘客回复',
  driverPending:'仍在等待司机回复。', riderPending:'仍在等待乘客回复。',
  smDriverReplies:'司机回复',
  catRoute:'路线', catNoShow:'取消费', catDamage:'清洁或损坏费', catSafety:'安全',
  tpSignedInAs:d => `已登录：${d}`, drvDriver:d => `司机：${d}`,
  drvNoCaseMsg:'打开案件后，这里会显示当前案件的司机。',
  mismatch:(t, s) => `这趟行程的工单类型是「${t}」，但您的描述听起来像「${s}」。是否仍按「${t}」处理这趟行程？`,
  mmYes:t => `是，按「${t}」继续`, existingCase:r => `这趟行程已有案件（${r}），正在打开。`,
  tpRiderConsole:'需要人工处理的您的案件会出现在这里。本演示中工作台只处理您本人的案件。',
});
const T = R.T, CUR = 'S$';
const $ = id => document.getElementById(id);
const mk = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const money = v => (typeof v === 'number' && isFinite(v)) ? CUR + v.toFixed(2) : String(v);

let me = null, health = null;
let caseId = null, status = null, streams = [], summary = null, qa = {}, busy = false;
let roomWorking = false, askBusy = false, decisionAction = null;
let stage = 'describe', storyParts = [], finding = false, queueTimer = null, showInitial = false;
let view = 'rider', driverCases = [], driverTimer = null;
let askedQs = [], understoodType = null;             // stage 1: clarifying questions already asked, the understood type
const driverWaiting = () => driverCases.reduce((n, c) => n + (c.waiting || 0), 0);
const HUMAN_ST = ['with_agent', 'waiting_for_rider', 'waiting_for_driver', 'waiting_for_both'];
const riderWaiting = st => st === 'waiting_for_rider' || st === 'waiting_for_both';

/* ---------------------------------------------------------------- live status indicators */
function setLive(pane, key, tone){
  const n = $('st-' + pane); if (!n) return;
  n.dataset.tone = tone || key;
  n.querySelector('span').textContent = (T('live') || {})[key] || key;
}
function refreshLive(){
  const inp = $('riderInput');
  if (view === 'driver'){
    const waiting = driverWaiting() > 0;
    setLive('rider', waiting ? 'replyNeeded' : 'online', waiting ? 'attn' : 'idle');
  }
  else if (finding) setLive('rider', 'finding', 'busy');
  else if (document.activeElement === inp && inp.value.trim()) setLive('rider', 'typing');
  else if (riderWaiting(status)) setLive('rider', 'waiting', 'attn');
  else if (status === 'resolved_by_ai' || status === 'resolved_by_human') setLive('rider', 'resolved', 'ok');
  else setLive('rider', 'online', 'idle');

  if (roomWorking) setLive('room', 'working', 'busy');
  else if (caseId && status !== 'intake') setLive('room', 'done', 'ok');
  else setLive('room', 'idle');

  if (askBusy) setLive('human', 'answering', 'busy');
  else if (status === 'with_agent') setLive('human', 'review', 'attn');
  else if (status === 'waiting_for_driver') setLive('human', 'waitingDriver', 'busy');
  else if (status === 'waiting_for_both') setLive('human', 'waitingBoth', 'busy');
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
  if (r.status === 401){ location.href = '/'; throw new Error(T('errGeneric')); }    // session gone: back to login
  let data = null; try { data = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((data && data.detail) || T('errGeneric'));
  return data;
}

/* ---------------------------------------------------------------- streams */
function subscribe(id){
  closeStreams();
  ['rider', 'room', 'human', 'driver'].forEach(pane => {
    const es = new EventSource(`/api/cases/${encodeURIComponent(id)}/events`);
    es.onmessage = e => {
      let ev; try { ev = JSON.parse(e.data); } catch (err){ return; }
      if (ev.case_id !== caseId) return;
      if (ev.pane === 'case'){ if (pane === 'rider') onStatus(ev); return; }   // status: handled once
      if (ev.pane !== pane) return;
      ({rider: onRider, room: onRoom, human: onHuman, driver: onDriver})[pane](ev);
      ping(pane);
    };
    streams.push(es);
  });
}
function closeStreams(){ streams.forEach(s => s.close()); streams = []; }

function onStatus(ev){
  status = ev.status;
  const bar = $('ticketBar');
  if (ev.reference && ev.reference.startsWith('DISP-')){ bar.hidden = view !== 'rider'; $('tbRef').textContent = ev.reference; }
  $('tbStatus').textContent = (T('rs') || {})[ev.status] || ev.status;
  $('tbStatus').dataset.s = ev.status;
  riderTyping(ev.status === 'intake' || ev.status === 'in_review');
  if (summary) renderSummary();
  syncDecisionBar(); syncRiderInput();
  loadQueue();
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
function riderTyping(on, label){
  let t = $('riderTyping');
  if (on && !t){
    t = mk('div', 'rm left rm-typing'); t.id = 'riderTyping';
    const b = mk('div', 'rm-bubble');
    b.innerHTML = '<span class="dots"><i></i><i></i><i></i></span>';
    if (label) b.appendChild(mk('span', 'rm-typing-lbl', label));
    t.appendChild(b);
    riderChat.appendChild(t);
  } else if (!on && t) t.remove();
  riderScroll();
}
function onRider(ev){
  switch (ev.type){
    case 'rider_message':
      if (ev.initial && !showInitial) break;           // already in the rider's own chat from stage 1
      riderRow('right', null, 'me').textContent = ev.text; break;
    case 'assistant_message': riderRow('left', T('sRyde')).textContent = ev.text; break;
    case 'support_typing': riderTyping(true); break;
    case 'support_message': riderTyping(false); riderRow('left', T('sSupport'), 'support').textContent = ev.text; break;
    case 'trip_choice': break;                         // trips are confirmed in stage 1 now
    case 'ticket_update': break;                       // the ticket bar follows the case status
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

/* ---- stage 1: find and confirm the trip */
const tripLabel = c => `${c.pickup} → ${c.dropoff}${c.time ? ', ' + R.fmtTime(c.time) : ''}`;
function tripCard(c, opts){
  const card = mk('div', 'tc');
  card.appendChild(mk('div', 'tc-route', `${c.pickup} → ${c.dropoff}`));
  const amt = c.fare != null ? (c.fare_kind === 'fee' ? T('feeOf')(money(c.fare)) : money(c.fare)) : null;
  const meta = [R.fmtTime(c.time), amt, T('st_' + c.status) || c.status].filter(Boolean).join(' · ');
  card.appendChild(mk('div', 'tc-meta', meta));
  if (c.why && opts.why !== false) card.appendChild(mk('div', 'tc-why', `${T('whyMatch')}: ${c.why}`));
  if (opts.button){
    const btn = mk('button', 'btn primary tc-btn', opts.button); btn.type = 'button';
    btn.addEventListener('click', () => chooseTrip(c));
    card.appendChild(btn);
  }
  return card;
}
function showPicker(msg, cards){
  const b = riderRow('left', T('sRyde'), 'picker');
  b.appendChild(mk('p', null, msg));
  const list = mk('div', 'tc-list'); list.setAttribute('role', 'list');
  cards.forEach(c => { const card = tripCard(c, {button: T('pickOne')}); card.setAttribute('role', 'listitem'); list.appendChild(card); });
  b.appendChild(list);
}
function showConfirm(res){
  const c = res.candidates[0];
  const b = riderRow('left', T('sRyde'), 'picker');
  b.appendChild(mk('p', null, res.message.replace(/ ?(Is this the one\?|是这一趟吗？)$/, '')));
  b.appendChild(tripCard(c, {}));
  b.appendChild(mk('p', 'tc-q', T('isThis')));
  const row = mk('div', 'tc-actions');
  const yes = mk('button', 'btn primary', T('yes')); yes.type = 'button';
  yes.addEventListener('click', () => chooseTrip(c));
  const no = mk('button', 'btn', T('noOther')); no.type = 'button';
  no.addEventListener('click', () => {
    disableCards(b);
    const others = (res.recent || []).filter(x => x.trip_id !== c.trip_id);
    showPicker(T('otherTrips'), others);
    riderScroll();
  });
  row.appendChild(yes); row.appendChild(no); b.appendChild(row);
}
/* the story sounds like another kind of dispute than the ticket on the chosen ride: ask, never override */
function showMismatch(c, mm){
  const b = riderRow('left', T('sRyde'), 'picker');
  b.appendChild(mk('p', null, T('mismatch')(mm.ticket_label, mm.story_label)));
  const row = mk('div', 'tc-actions');
  const yes = mk('button', 'btn primary', T('mmYes')(mm.ticket_label)); yes.type = 'button';
  yes.addEventListener('click', () => { disableCards(b); chooseTrip(c, true); });
  const no = mk('button', 'btn', T('noOther')); no.type = 'button';
  no.addEventListener('click', () => { disableCards(b); storyParts.length && findTripList(); });
  row.appendChild(yes); row.appendChild(no); b.appendChild(row);
  riderScroll();
}
async function findTripList(){
  try {
    const res = await api('/api/rider/find-trip', {story: 'Show me all my rides.', lang: R.getLang()});
    showPicker(res.message, res.candidates || []);
  } catch (e){ riderRow('left', T('sRyde'), 'error').textContent = e.message; }
  riderScroll();
}
function disableCards(scope){ (scope || riderChat).querySelectorAll('.picker button').forEach(x => { x.disabled = true; }); }

/* every intake answer says where it came from: the model ("Live AI") or the keyword fallback, with the reason */
function intakeBadge(bubble, intake){
  if (!intake || !intake.badge) return;
  const b = mk('span', 'intake-badge ' + (intake.source === 'llm' ? 'live' : intake.source === 'rider_choice' ? 'choice' : 'rules'), intake.badge);
  if (intake.reason) b.title = intake.reason;
  bubble.parentElement.insertBefore(b, bubble);
}
function showNotice(text){
  const n = mk('div', 'rm-notice', text); n.setAttribute('role', 'status');
  riderChat.insertBefore(n, $('riderTyping') || null);
}
function showCategoryButtons(res){
  const b = riderRow('left', T('sRyde'), 'picker');
  b.appendChild(mk('p', null, res.message));
  const row = mk('div', 'tc-actions');
  [['route_deviation', 'catRoute'], ['no_show_charge', 'catNoShow'], ['property_damage', 'catDamage'], ['safety_incident', 'catSafety']]
    .forEach(([type, key]) => {
      const btn = mk('button', 'btn', T(key)); btn.type = 'button';
      btn.addEventListener('click', () => { disableCards(b); riderRow('right', null, 'me').textContent = T(key); findTrip(type); });
      row.appendChild(btn);
    });
  b.appendChild(row);
  intakeBadge(b, res.intake);
}
async function findTrip(category){
  finding = true; refreshLive(); riderTyping(true, T('finding'));
  try {
    // the whole conversation every time: a later message adds to the earlier ones
    const res = await api('/api/rider/find-trip', {messages: storyParts, asked: askedQs, category: category || null,
                                                   mode: $('modeSelect').value, lang: R.getLang()});
    riderTyping(false);
    if (res.intake && res.intake.notice) showNotice(res.intake.notice);
    understoodType = res.intake && res.intake.dispute_type !== 'unclear' ? res.intake.dispute_type : null;
    let bubble = null;
    if (res.state === 'clarify' || res.state === 'foreign'){
      bubble = riderRow('left', T('sRyde')); bubble.textContent = res.message;
      if (res.state === 'clarify') askedQs.push(res.message);
      if (res.state === 'foreign'){ storyParts = []; askedQs = []; }          // that story is dropped, not matched later
    }
    else if (res.state === 'choose_category'){ showCategoryButtons(res); return; }
    else if (res.state === 'none') showPicker(res.message, res.recent || []);
    else if (res.state === 'list') showPicker(res.message, res.candidates || []);
    else if (res.state === 'confirm') showConfirm(res);
    else showPicker(res.message, res.candidates || []);
    if (!bubble){ const all = riderChat.querySelectorAll('.rm.left .rm-bubble'); bubble = all[all.length - 1]; }
    if (bubble) intakeBadge(bubble, res.intake);
  } catch (e){
    riderTyping(false); riderRow('left', T('sRyde'), 'error').textContent = e.message;
  } finally { finding = false; refreshLive(); riderScroll(); }
}

async function chooseTrip(c, confirmType){
  if (busy || caseId) return;
  disableCards();
  if (!confirmType) riderRow('right', null, 'me').textContent = T('chose')(tripLabel(c));
  busy = true; syncRiderInput();
  try {
    const r = await fetch('/api/cases', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({story: storyParts.join('\n'), trip_id: c.trip_id, mode: $('modeSelect').value, lang: R.getLang(),
                            confirm_type: !!confirmType, category: understoodType})});
    if (r.status === 401){ location.href = '/'; return; }
    const snap = await r.json();
    if (r.status === 409 && snap.mismatch){ showMismatch(c, snap.mismatch); return; }
    if (!r.ok) throw new Error(snap.detail || T('errGeneric'));
    if (snap.existing){                                   // this ride already has a case: open that one
      busy = false; openCase(snap.id);
      riderRow('left', T('sRyde')).textContent = T('existingCase')(snap.reference);
      return;
    }
    showInitial = false;
    caseId = snap.id; status = snap.status; roomWorking = true; stage = 'case';
    R.reset(); $('chat').querySelectorAll('.empty-state').forEach(n => n.remove());
    subscribe(caseId);
  } catch (e){
    riderRow('left', T('sRyde'), 'error').textContent = e.message;
  } finally { busy = false; syncRiderInput(); refreshLive(); riderScroll(); }
}

async function sendRider(text){
  text = (text || '').trim();
  if (!text || busy || finding) return;
  if (view === 'driver') return sendDriverReply(text);
  if (caseId && (status === 'resolved_by_ai' || status === 'resolved_by_human')) resetCase();
  busy = true; $('riderSend').disabled = true;
  try {
    if (!caseId){                                    // stage 1: nothing exists yet but the rider's words
      riderRow('right', null, 'me').textContent = text;
      storyParts.push(text);
      $('riderInput').value = ''; growRider();
      busy = false;
      await findTrip();
    } else {
      await api(`/api/cases/${caseId}/rider-message`, {text});
      $('riderInput').value = ''; growRider();
    }
  } catch (e){
    riderRow('left', T('sRyde'), 'error').textContent = e.message;
  } finally {
    busy = false; syncRiderInput(); refreshLive(); riderScroll();      // never leave Send stuck
  }
}
function syncRiderInput(){
  const noQuestion = view === 'driver' && driverWaiting() === 0;
  $('riderSend').disabled = busy || finding || noQuestion;
}

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
  // the room's own events say whether the agents are working (the status stream can arrive out of order)
  if (ev.type === 'done' || ev.type === 'error') roomWorking = false;
  else if (ev.type !== 'system_note' && ev.type !== 'rider_message') roomWorking = true;
  refreshLive();
}
function roomIdle(){
  R.reset();
  const es = mk('div', 'empty-state', T('tpRoomEmpty')); es.dataset.i18n = 'tpRoomEmpty';
  $('chat').insertBefore(es, $('typingZone'));
}

/* ---------------------------------------------------------------- RIGHT: support console */
function onHuman(ev){
  if (ev.type === 'case_escalated' || ev.type === 'summary'){ summary = ev.summary; renderSummary(); showConsole(); }
  else if (ev.type === 'qa'){ qa[ev.entry.id] = ev.entry; renderQA(); renderBadges(); }
  else if (ev.type === 'rider_message'){ qa['r' + ev.seq] = {id: 'r' + ev.seq, kind: 'rider', text: ev.text, at: ev.at}; renderQA(); }
  else if (ev.type === 'decision'){ renderDecided(ev.decision); }
  syncDecisionBar(); refreshLive();
}
function showConsole(){ $('consoleIdle').hidden = true; $('consoleCase').hidden = false; }

/* the console's queue: this rider's own cases that were handed to a person */
let queue = [];
async function loadQueue(){
  try { queue = ((await api('/api/cases')).cases || []).filter(c => c.escalated); } catch (e) { return; }
  renderQueue();
}
function renderQueue(){
  const box = $('queue'), list = $('queueList');
  box.hidden = !queue.length; list.innerHTML = '';
  queue.slice().reverse().forEach(c => {
    const st = c.id === caseId ? status : c.status;
    const b = mk('button', 'q-item' + (c.id === caseId ? ' on' : '')); b.type = 'button';
    b.appendChild(mk('span', 'q-ref', c.reference));
    b.appendChild(mk('span', 'q-meta', [R.typeLabel(c.dispute_type || ''), c.trip_id].filter(Boolean).join(' · ')));
    b.appendChild(mk('span', 'q-st q-' + st, (T('hs') || {})[st] || st));
    b.setAttribute('aria-current', c.id === caseId ? 'true' : 'false');
    b.addEventListener('click', () => openCase(c.id));
    list.appendChild(b);
  });
  if (!caseId) $('consoleIdle').hidden = queue.length > 0;
}
function openCase(id){
  if (id === caseId) return;
  clearCaseViews();
  caseId = id; roomWorking = false; showInitial = true;     // an earlier case: replay its whole conversation
  R.reset(); $('chat').querySelectorAll('.empty-state').forEach(n => n.remove());
  subscribe(id); renderQueue();
}

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

  card.appendChild(block(T('smWhy'), R.bullets(s.escalation_reasons || []), 'why'));
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
  if ((s.driver_replies || []).length)
    card.appendChild(block(T('smDriverReplies'), R.bullets(s.driver_replies.map(m => `${R.fmtTime(m.at)} · ${m.text}`))));
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
    const head = mk('div', 'qa-head');
    // who the question went to (or that the record answered it), and where it stands
    const to = e.recipient === 'driver' ? T('toDriver') : e.recipient === 'rider' ? T('toRider') : (e.status === 'answering' ? '' : T('fromRecord'));
    if (to) head.appendChild(mk('span', 'qa-to qa-to-' + (e.recipient || 'record'), to));
    const st = {answering:'qaAnswering', answered:'qaAnsweredLbl', asked_rider: e.kind === 'info_request' ? 'qaInfo' : 'qaSent',
                asked_driver:'qaSent', answered_after_reply:'qaAnsweredLbl'}[e.status];
    if (st) head.appendChild(mk('span', 'qa-status', T(st)));
    d.appendChild(head);
    d.appendChild(mk('div', 'qa-q', e.question));
    if (e.original && e.original !== e.question) d.appendChild(mk('div', 'qa-orig', `${T('qaYouWrote')}: ${e.original}`));
    if (e.route_reason && e.recipient) d.appendChild(mk('div', 'qa-orig', e.route_reason));
    if (e.status === 'answered' || e.status === 'answered_after_reply'){
      if (e.answer) d.appendChild(mk('div', 'qa-a', e.answer));
      if ((e.citations || []).length){
        const c = mk('div', 'qa-cites'); c.appendChild(mk('span', 'sm-k', T('qaSources')));
        c.appendChild(R.tagList([...new Set(e.citations)], 'blue')); d.appendChild(c);
      }
    } else if (e.answer && e.status !== 'answering') d.appendChild(mk('div', 'qa-a', e.answer));
    const sent = e.sent_to_driver || e.sent_to_rider;
    if (sent) d.appendChild(mk('div', 'qa-sent', `${e.sent_to_driver ? T('toDriver') : T('toRider')}: ${sent}`));
    if (e.reply) d.appendChild(mk('div', 'qa-reply', `${e.reply_from === 'driver' ? T('driverReplied') : T('riderReplied')}: ${e.reply.text}`));
    th.appendChild(d);
  });
  const sc = $('consoleScroll'); sc.scrollTop = sc.scrollHeight;
}

/* ask: rephrase first, then who it would go to (Auto / Rider / Driver); the person confirms or edits both the
   question and the wording the rider or driver would receive; then the case-QA agent answers from the record,
   and only if the record has no answer is the question sent. */
let partySeq = 0;
async function previewParty(){
  const to = $('qcTo').value, q = $('qcEdit').value.trim(), my = ++partySeq;
  $('qcPartyLbl').textContent = T('willReceive')(to === 'driver' ? T('askDriver').toLowerCase() : T('askRider').toLowerCase());
  if (!q) return;
  try {
    const r = await api(`/api/cases/${caseId}/human/rephrase`, {text: q, purpose: to});
    if (my === partySeq) $('qcParty').value = r.rephrased;
  } catch (err){ $('qcNote').textContent = err.message; }
}
$('askForm').addEventListener('submit', async e => {
  e.preventDefault();
  const text = $('askInput').value.trim(); if (!text || !caseId || askBusy) return;
  askBusy = true; $('askBtn').disabled = true; refreshLive();
  try {
    const r = await api(`/api/cases/${caseId}/human/rephrase`, {text, purpose: 'qa'});
    $('qcOrig').textContent = r.original; $('qcEdit').value = r.rephrased;
    $('qcNote').textContent = r.changed ? T('tpChanged') : T('tpUnchanged');
    const pick = $('askTo').value;
    if (pick === 'auto'){
      const route = await api(`/api/cases/${caseId}/human/route`, {question: r.rephrased});
      $('qcTo').value = route.recipient; $('qcReason').textContent = route.reason;
    } else { $('qcTo').value = pick; $('qcReason').textContent = ''; }
    await previewParty();
    $('askForm').hidden = true; $('askConfirm').hidden = false; $('qcEdit').focus();
  } catch (err){ $('qcNote').textContent = err.message; }
  finally { askBusy = false; syncDecisionBar(); refreshLive(); }
});
$('qcTo').addEventListener('change', () => { $('qcReason').textContent = ''; previewParty(); });
$('qcCancel').addEventListener('click', () => { $('askConfirm').hidden = true; $('askForm').hidden = false; $('askInput').focus(); });
$('qcSend').addEventListener('click', async () => {
  const q = $('qcEdit').value.trim(); if (!q || askBusy) return;
  askBusy = true; $('qcSend').disabled = true; refreshLive();
  try {
    await api(`/api/cases/${caseId}/human/ask`, {question: q, original: $('qcOrig').textContent,
      recipient: $('qcTo').value, party_text: $('qcParty').value.trim() || null});
    $('askInput').value = ''; $('askConfirm').hidden = true; $('askForm').hidden = false;
  } catch (err){ $('qcNote').textContent = err.message; }
  finally { askBusy = false; $('qcSend').disabled = false; syncDecisionBar(); refreshLive(); }
});

/* decision bar */
function syncDecisionBar(){
  const bar = $('decisionBar');
  const open = HUMAN_ST.includes(status);
  const pend = Object.values(qa).filter(e => e.status === 'asked_driver').length;
  const pendR = Object.values(qa).filter(e => e.status === 'asked_rider').length;
  $('dbPending').textContent = [pend ? T('driverPending') : '', pendR ? T('riderPending') : ''].filter(Boolean).join(' ');
  $('dbPending').hidden = !(pend || pendR);
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

/* ---------------------------------------------------------------- demo strip, identity, reset */
function renderFills(){
  const box = $('fills'); box.innerHTML = '';
  const stories = (me && me.stories) || [];
  $('fills').parentElement.querySelector('.tp-fill-lbl').hidden = !stories.length;
  stories.forEach(st => {
    const lang = R.getLang();
    const b = mk('button', 'chip', lang === 'zh' ? st.label_zh : st.label_en); b.type = 'button';
    b.addEventListener('click', () => {           // fills the text box only; never sends
      const i = $('riderInput'); i.value = lang === 'zh' ? st.zh : st.en; growRider(); i.focus(); showPane('rider'); refreshLive();
    });
    box.appendChild(b);
  });
}
function renderIdentity(){
  // name and id exactly as in the dataset, e.g. "Wong Mei Ling (R-3312)"
  $('whoami').textContent = T('tpSignedInAs')(me.display);
}
function greet(){
  riderRow('left', T('sRyde')).textContent = T('hello')(me.display);
}

/* ---------------------------------------------------------------- LEFT: driver view (receive and reply only)
   A demo pane of the signed-in rider's own cases: each case shows its own driver (resolved on the server from
   the trip), support's questions, and the reply box. No driver login, no driver chooser. */
const driverChat = $('driverChat');
function driverScroll(){ driverChat.scrollTop = driverChat.scrollHeight; }
function driverTyping(on){
  let t = $('driverTyping');
  if (on && !t){
    t = mk('div', 'rm left rm-typing'); t.id = 'driverTyping';
    t.appendChild(mk('div', 'rm-who', T('sSupport')));
    const b = mk('div', 'rm-bubble'); b.innerHTML = '<span class="dots"><i></i><i></i><i></i></span>';
    t.appendChild(b); driverChat.appendChild(t);
  } else if (!on && t) t.remove();
  driverScroll();
}
function renderDriverView(){
  driverChat.querySelectorAll('.drv-case, .drv-err').forEach(n => n.remove());
  // the active case first, then the rider's other cases
  const cases = driverCases.slice().sort((a, b) => (b.case_id === caseId) - (a.case_id === caseId));
  cases.forEach(c => {
    if (c.case_id !== caseId && !c.questions.length) return;
    const host = mk('section', 'drv-case'); host.dataset.case = c.case_id;
    const head = mk('div', 'drv-head');
    head.appendChild(mk('span', 'drv-name', T('drvDriver')(`${c.driver.name} (${c.driver.id})`)));
    head.appendChild(mk('span', 'drv-ref', c.reference));
    host.appendChild(head);
    const card = mk('div', 'tc drv-trip');
    card.appendChild(mk('div', 'tc-route', `${c.trip.pickup || '?'} → ${c.trip.dropoff || '?'}`));
    card.appendChild(mk('div', 'tc-meta', R.fmtTime(c.trip.date)));
    host.appendChild(card);
    c.questions.forEach(q => {
      const row = mk('div', 'rm left support'); row.appendChild(mk('div', 'rm-who', `${T('sSupport')} · ${q.reference}`));
      const b = mk('div', 'rm-bubble');
      if (q.rider_first_name) b.appendChild(mk('div', 'drv-rider', T('drvRider')(q.rider_first_name)));
      b.appendChild(mk('p', 'drv-text', q.text));
      row.appendChild(b); host.appendChild(row);
      if (q.reply){
        const me_ = mk('div', 'rm right me'); me_.appendChild(mk('div', 'rm-bubble', q.reply.text)); host.appendChild(me_);
        const ack = mk('div', 'rm left'); ack.appendChild(mk('div', 'rm-who', 'Ryde')); ack.appendChild(mk('div', 'rm-bubble', T('drvAck')));
        host.appendChild(ack);
      }
    });
    driverChat.insertBefore(host, $('driverTyping') || null);
  });
  $('driverEmpty').hidden = driverCases.some(c => c.questions.length);
  $('driverNoCase').hidden = driverCases.some(c => c.case_id === caseId);
  driverScroll(); syncRiderInput(); refreshLive(); renderBadges();
}
async function loadDriverView(){
  try { driverCases = (await api('/api/driver-view')).cases || []; } catch (e){ return; }
  renderDriverView();
}
function onDriver(ev){
  if (ev.type === 'support_typing') driverTyping(true);
  else { driverTyping(false); loadDriverView(); }
}
async function sendDriverReply(text){
  // the newest waiting question, on the active case first
  const order = driverCases.slice().sort((a, b) => (b.case_id === caseId) - (a.case_id === caseId));
  let target = null;
  for (const c of order){
    const w = c.questions.filter(q => q.status === 'waiting');
    if (w.length){ target = {case_id: c.case_id, question_id: w[w.length - 1].id}; break; }
  }
  if (!target){ const e = mk('div', 'rm left drv-err'); e.appendChild(mk('div', 'rm-bubble', T('drvNoPending'))); driverChat.appendChild(e); return; }
  busy = true; syncRiderInput();
  try {
    await api('/api/driver-view/reply', {...target, text});
    $('riderInput').value = ''; growRider();
    await loadDriverView();
  } catch (e){ const n = mk('div', 'rm left drv-err'); n.appendChild(mk('div', 'rm-bubble', e.message)); driverChat.appendChild(n); }
  finally { busy = false; syncRiderInput(); refreshLive(); $('riderInput').focus(); }
}

/* the Rider | Driver toggle: only switches which view of the rider's own cases is shown */
function applyView(v){
  view = v;
  $('tgRider').setAttribute('aria-pressed', v === 'rider' ? 'true' : 'false');
  $('tgDriver').setAttribute('aria-pressed', v === 'driver' ? 'true' : 'false');
  riderChat.hidden = v !== 'rider'; driverChat.hidden = v !== 'driver';
  $('ticketBar').hidden = v !== 'rider' || !(caseId && $('tbRef').textContent);
  $('phoneSub').textContent = v === 'driver' ? T('drvHelp') : T('tpHelp');
  $('riderInput').placeholder = v === 'driver' ? T('drvPh') : T('tpRiderPh');
  const stories = ((me && me.stories) || []).length;
  $('fills').hidden = v === 'driver'; document.querySelector('.tp-fill-lbl').hidden = v === 'driver' || !stories;
  syncRiderInput(); refreshLive();
  $('riderInput').focus();
}
async function setView(v){
  if (v === view) return;
  applyView(v);
  if (v === 'driver') await loadDriverView();
}
$('tgRider').addEventListener('click', () => setView('rider'));
$('tgDriver').addEventListener('click', () => setView('driver'));
function badge(btn, n){ const b = btn.querySelector('.tg-badge'); b.hidden = !n; b.textContent = n || ''; }
function renderBadges(){
  badge($('tgRider'), Object.values(qa).filter(e => e.status === 'asked_rider').length);
  badge($('tgDriver'), driverWaiting());
}

function clearCaseViews(){
  closeStreams();
  status = null; summary = null; qa = {}; roomWorking = false; askBusy = false; decisionAction = null;
  riderChat.querySelectorAll('.rm').forEach(n => n.remove());
  $('ticketBar').hidden = true;
  $('summary').innerHTML = ''; $('qaThread').innerHTML = '';
  $('consoleIdle').hidden = false; $('consoleCase').hidden = true;
  $('askConfirm').hidden = true; $('askForm').hidden = false; $('dbForm').hidden = true;
  const done = $('decisionBar').querySelector('.db-done'); if (done) done.remove();
  renderBadges();
}
function resetCase(){
  clearCaseViews();
  caseId = null; stage = 'describe'; storyParts = []; finding = false; busy = false; showInitial = false;
  askedQs = []; understoodType = null;
  roomIdle();
  $('riderEmpty').hidden = true;
  greet();
  loadQueue(); loadDriverView();
  syncDecisionBar(); syncRiderInput(); refreshLive();
}
$('resetBtn').addEventListener('click', resetCase);
$('signOutBtn').addEventListener('click', async () => {
  closeStreams();
  try { await fetch('/api/auth/logout', {method: 'POST'}); } catch (e) {}
  location.href = '/';
});
$('langSelect').addEventListener('change', e => {
  R.setLang(e.target.value); renderFills(); renderIdentity(); refreshLive();
  applyView(view); renderDriverView();
  if (status) $('tbStatus').textContent = (T('rs') || {})[status] || status;
  renderSummary(); renderQA(); renderQueue();
});

async function boot(){
  $('langSelect').value = R.getLang();
  R.applyStatic();
  try { me = await api('/api/auth/me'); } catch (e) { return; }      // 401: api() already went to the login page
  renderIdentity(); renderFills();
  $('riderEmpty').hidden = true;
  greet();
  loadQueue(); queueTimer = setInterval(loadQueue, 4000);
  loadDriverView(); driverTimer = setInterval(() => { if (view === 'driver' || caseId) loadDriverView(); }, 4000);
  refreshLive(); syncDecisionBar(); syncRiderInput();
  try {
    health = await api('/api/health');
    const llmOpt = $('modeSelect').querySelector('option[value="llm"]');
    if (!health.has_api_key){ llmOpt.disabled = true; $('modeSelect').value = 'deterministic'; }
    else $('modeSelect').value = health.llm_mode === 'llm' ? 'llm' : 'deterministic';
  } catch (e) { $('modeSelect').value = 'deterministic'; }
}
boot();
})();
