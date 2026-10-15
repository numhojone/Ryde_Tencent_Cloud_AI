/* Ryde Support demo login: pick a demo rider, driver or the support agent and sign in. No password: demo only.
   The server signs a session cookie; every later request takes the rider_id from that cookie. */
(() => {
const R = window.RoomUI;
Object.assign(R.I18N.en, {
  tpTitle:'Ryde Support | Sign in', lgTitle:'Ryde Support', lgSub:'Get help with a trip', lgRoleTitle:'Sign in as',
  lgRider:'Rider', lgDriver:'Driver', lgSupport:'Support agent', lgAccount:'Rider account', lgDriverAccount:'Driver account',
  lgDriverNote:'Drivers only see questions from Ryde Support about their own trips, and reply to them.', lgNote:'Demo accounts. No password needed.',
  lgSupportNote:'Handles cases the AI has passed to a person, from any rider.', lgSignIn:'Sign in', lgSigning:'Signing in…',
  lgFoot:'Tip: to play the rider and the support agent at the same time, sign in as the support agent in a private window.',
  lgFail:'Could not sign in. Please try again.',
});
Object.assign(R.I18N.zh, {
  tpTitle:'Ryde 客服 | 登录', lgTitle:'Ryde 客服', lgSub:'行程问题求助', lgRoleTitle:'登录身份',
  lgRider:'乘客', lgDriver:'司机', lgSupport:'客服专员', lgAccount:'乘客账户', lgDriverAccount:'司机账户',
  lgDriverNote:'司机只能看到 Ryde 客服就其本人行程提出的问题，并作出回复。', lgNote:'演示账户，无需密码。',
  lgSupportNote:'处理 AI 转交人工的案件，可查看任何乘客的案件。', lgSignIn:'登录', lgSigning:'登录中…',
  lgFoot:'提示：如需同时扮演乘客和客服专员，请在无痕窗口中以客服专员身份登录。',
  lgFail:'登录失败，请重试。',
});
const $ = id => document.getElementById(id);
const role = () => document.querySelector('input[name="role"]:checked').value;

function syncRole(){
  const r = role();
  $('riderField').hidden = r !== 'rider'; $('driverField').hidden = r !== 'driver';
  $('driverNote').hidden = r !== 'driver'; $('supportNote').hidden = r !== 'support';
  $('accountSelect').required = r === 'rider';
}
document.querySelectorAll('input[name="role"]').forEach(r => r.addEventListener('change', syncRole));

$('langSelect').addEventListener('change', e => R.setLang(e.target.value));

$('loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('signInBtn'); btn.disabled = true; btn.textContent = R.T('lgSigning'); $('loginErr').textContent = '';
  const r = role();
  const body = r === 'support' ? {role: 'support'} : r === 'driver' ? {role: 'driver', driver_id: $('driverSelect').value}
    : {rider_id: $('accountSelect').value};
  try {
    const res = await fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    if (!res.ok) throw new Error();
    location.href = '/';
  } catch (err){
    $('loginErr').textContent = R.T('lgFail');
    btn.disabled = false; btn.textContent = R.T('lgSignIn');
  }
});

async function boot(){
  $('langSelect').value = R.getLang();
  R.applyStatic(); syncRole();
  try {
    const d = await fetch('/api/auth/accounts').then(r => r.json());
    const sel = $('accountSelect');
    (d.riders || []).forEach(a => {
      const o = document.createElement('option'); o.value = a.rider_id; o.textContent = `${a.name} (${a.rider_id})`;
      sel.appendChild(o);
    });
    (d.drivers || []).forEach(a => {
      const o = document.createElement('option'); o.value = a.driver_id; o.textContent = `${a.name} (${a.driver_id})`;
      $('driverSelect').appendChild(o);
    });
  } catch (e) { $('loginErr').textContent = R.T('lgFail'); }
}
boot();
})();
