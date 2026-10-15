/* Ryde Support demo login: pick one of the dataset's riders and sign in. No password: demo only. One role only.
   The server signs a session cookie; every later request takes the rider_id from that cookie. */
(() => {
const R = window.RoomUI;
Object.assign(R.I18N.en, {
  tpTitle:'Ryde Support | Sign in', lgTitle:'Ryde Support', lgSub:'Get help with a trip', lgAccount:'Rider account',
  lgNote:'Demo accounts. No password needed.', lgSignIn:'Sign in', lgSigning:'Signing in…',
  lgFoot:'After signing in you will see your own rides only. The agent room, the support console and the driver view on the next screen are demo panes for your own cases.',
  lgFail:'Could not sign in. Please try again.',
});
Object.assign(R.I18N.zh, {
  tpTitle:'Ryde 客服 | 登录', lgTitle:'Ryde 客服', lgSub:'行程问题求助', lgAccount:'乘客账户',
  lgNote:'演示账户，无需密码。', lgSignIn:'登录', lgSigning:'登录中…',
  lgFoot:'登录后只会看到您自己的行程。下一页中的智能体会话、客服工作台和司机视图都是针对您本人案件的演示面板。',
  lgFail:'登录失败，请重试。',
});
const $ = id => document.getElementById(id);

$('langSelect').addEventListener('change', e => R.setLang(e.target.value));

$('loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('signInBtn'); btn.disabled = true; btn.textContent = R.T('lgSigning'); $('loginErr').textContent = '';
  const body = {rider_id: $('accountSelect').value};
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
  R.applyStatic();
  try {
    const d = await fetch('/api/auth/accounts').then(r => r.json());
    const sel = $('accountSelect');
    (d.riders || []).forEach(a => {
      const o = document.createElement('option'); o.value = a.rider_id; o.textContent = `${a.name} (${a.rider_id})`;
      sel.appendChild(o);
    });
  } catch (e) { $('loginErr').textContent = R.T('lgFail'); }
}
boot();
})();
