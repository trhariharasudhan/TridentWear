import { mountChrome, $, $$, esc, icon, inr, img, toast, busy, params, fmtDate } from '../ui.js';
import { session } from '../store.js';
import { api, getMode } from '../api.js';

await mountChrome({ page: 'account' });
const root = $('[data-account]');
const next = params().get('next');
const safeNext = next && /^[a-z0-9-]+\.html(\?[^#]*)?$/i.test(next) ? next : null; // only same-site pages

const user = await session.load();
user ? renderAccount(user) : renderAuth(location.hash === '#register' ? 'register' : 'login');

// ------------------------------------------------------------------ auth screens
function shell(inner) {
  root.innerHTML = `<div class="auth">
    <div class="auth__art"><div><span class="eyebrow" style="color:var(--amber)">Members get more</span>
      <h1 class="h1" style="margin-top:12px;max-width:12ch">Join the Trident list</h1>
      <p style="color:#c5c8d3;max-width:36ch">Track orders, save your fits, early access to drops and 20% off your first order with TRIDENTFIRST.</p></div>
      <img src="assets/images/products/violet-signal-tee-back.webp" alt=""></div>
    <div class="auth__form"><div class="auth__card">${inner}</div></div></div>`;
}
function after(u) {
  session.set(u);
  toast(`Welcome${u?.name ? ', ' + u.name.split(' ')[0] : ''}!`);
  if (safeNext) location.href = safeNext;
  else if (u?.role === 'admin') location.href = 'admin.html';
  else renderAccount(u);
}

async function renderAuth(tab = 'login') {
  const demo = (await getMode()) === 'demo';
  shell(`
    <div class="tabs" role="tablist"><button data-tab="login" class="${tab === 'login' ? 'is-on' : ''}">Sign in</button><button data-tab="register" class="${tab === 'register' ? 'is-on' : ''}">Create account</button></div>
    <div data-pane></div>
    ${demo ? `<p class="dev-hint">Preview mode: accounts are stored in this browser only. Admin demo login: <b>admin@tridentwear.in</b> / <b>Admin@123</b></p>` : ''}`);
  $$('[data-tab]').forEach((b) => b.addEventListener('click', () => renderAuth(b.dataset.tab)));
  tab === 'login' ? loginPane() : registerPane();
}

function loginPane(method = 'email') {
  const pane = $('[data-pane]');
  pane.innerHTML = method === 'email' ? `
    <form style="display:grid;gap:14px" data-login novalidate>
      <h2 class="h2" style="font-size:28px">Welcome back</h2>
      <label class="field"><span>Email</span><input class="input" type="email" name="email" required autocomplete="email"></label>
      <label class="field"><span>Password</span><input class="input" type="password" name="password" required autocomplete="current-password"></label>
      <a class="linkish" data-forgot style="justify-self:end">Forgot password?</a>
      <p class="form-error" data-err></p>
      <button class="btn btn--block">Sign in</button>
      <div class="divider">or</div>
      <button type="button" class="btn btn--ghost btn--block" data-phone>${icon.phone}<span>Sign in with mobile OTP</span></button>
    </form>` : `
    <form style="display:grid;gap:14px" data-otp-form novalidate>
      <h2 class="h2" style="font-size:28px">Mobile sign in</h2>
      <label class="field"><span>Mobile number</span><div style="display:flex;gap:8px"><span class="input" style="width:70px;display:grid;place-items:center">+91</span><input class="input" name="phone" inputmode="tel" pattern="[6-9][0-9]{9}" maxlength="10" required autocomplete="tel-national"></div></label>
      <div data-otp-step hidden><label class="field"><span>Enter the 6-digit OTP</span></label><div class="otp">${Array(6).fill('<input inputmode="numeric" maxlength="1" aria-label="OTP digit">').join('')}</div><p data-hint></p></div>
      <p class="form-error" data-err></p>
      <button class="btn btn--block" data-otp-btn>Send OTP</button>
      <button type="button" class="linkish" data-email style="justify-self:center">Use email instead</button>
    </form>`;
  if (method === 'email') {
    $('[data-phone]').addEventListener('click', () => loginPane('phone'));
    $('[data-forgot]').addEventListener('click', forgotPane);
    $('[data-login]').addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      const btn = $('button.btn', e.target); const err = $('[data-err]', e.target);
      if (!e.target.checkValidity()) { err.textContent = 'Enter your email and password.'; return; }
      busy(btn, true);
      try { after(await api.login(f.email, f.password)); }
      catch (ex) {
        busy(btn, false); err.textContent = ex.message;
        if (/verify/i.test(ex.message)) verifyPane(f.email);
      }
    });
  } else {
    $('[data-email]').addEventListener('click', () => loginPane('email'));
    const form = $('[data-otp-form]'); const btn = $('[data-otp-btn]'); const err = $('[data-err]', form);
    wireOtpBoxes(form);
    let sent = false;
    form.addEventListener('submit', async (e) => {
      e.preventDefault(); err.textContent = '';
      const phone = form.phone.value.trim();
      if (!/^[6-9]\d{9}$/.test(phone)) { err.textContent = 'Enter a valid 10-digit mobile number.'; return; }
      busy(btn, true);
      try {
        if (!sent) {
          const r = await api.sendOtp(phone);
          sent = true; $('[data-otp-step]').hidden = false; busy(btn, false); btn.textContent = 'Verify & sign in';
          $('[data-hint]').innerHTML = r?.dev_otp ? `<span class="dev-hint" style="display:block">Dev/test OTP: <b>${esc(r.dev_otp)}</b> (SMS provider not configured)</span>` : '<span class="muted">OTP sent by SMS.</span>';
          $('.otp input', form).focus();
        } else {
          const otp = $$('.otp input', form).map((i) => i.value).join('');
          if (otp.length !== 6) { busy(btn, false); err.textContent = 'Enter all 6 digits.'; return; }
          after(await api.verifyOtp(phone, otp));
        }
      } catch (ex) { busy(btn, false); err.textContent = ex.message; }
    });
  }
}

function registerPane() {
  $('[data-pane]').innerHTML = `
    <form style="display:grid;gap:14px" data-reg novalidate>
      <h2 class="h2" style="font-size:28px">Create account</h2>
      <label class="field"><span>Full name</span><input class="input" name="name" required minlength="2" autocomplete="name"></label>
      <label class="field"><span>Email</span><input class="input" type="email" name="email" required autocomplete="email"></label>
      <label class="field"><span>Password</span><input class="input" type="password" name="password" required minlength="8" autocomplete="new-password"><small class="muted">8+ characters with a number and a letter.</small></label>
      <label class="check"><input type="checkbox" required name="terms"> I agree to the <a class="linkish" href="policies.html#terms">terms</a> & <a class="linkish" href="policies.html#privacy">privacy policy</a></label>
      <p class="form-error" data-err></p>
      <button class="btn btn--block">Create account</button>
    </form>`;
  $('[data-reg]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target; const err = $('[data-err]', form); const btn = $('button.btn', form);
    const f = Object.fromEntries(new FormData(form));
    if (!form.checkValidity()) { err.textContent = 'Please complete all fields (password 8+ characters) and accept the terms.'; return; }
    if (!/[A-Za-z]/.test(f.password) || !/\d/.test(f.password)) { err.textContent = 'Password needs at least one letter and one number.'; return; }
    busy(btn, true);
    try {
      const r = await api.register({ name: f.name.trim(), email: f.email.trim(), password: f.password, confirm_password: f.password });
      verifyPane(f.email, r?.dev_otp, f.password);
    } catch (ex) { busy(btn, false); err.textContent = ex.message; }
  });
}

function verifyPane(email, devOtp, password) {
  $('[data-pane]').innerHTML = `
    <form style="display:grid;gap:14px" data-verify novalidate>
      <h2 class="h2" style="font-size:28px">Verify your email</h2>
      <p class="muted" style="margin:0">We sent a 6-digit code to <b>${esc(email)}</b>.</p>
      <div class="otp">${Array(6).fill('<input inputmode="numeric" maxlength="1" aria-label="OTP digit">').join('')}</div>
      ${devOtp ? `<p class="dev-hint">Email isn't configured on this server yet, so here's your code: <b>${esc(devOtp)}</b></p>` : ''}
      <p class="form-error" data-err></p>
      <button class="btn btn--block">Verify</button>
    </form>`;
  const form = $('[data-verify]'); wireOtpBoxes(form);
  $('.otp input', form).focus();
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const otp = $$('.otp input', form).map((i) => i.value).join('');
    const btn = $('button.btn', form); const err = $('[data-err]', form);
    if (otp.length !== 6) { err.textContent = 'Enter all 6 digits.'; return; }
    busy(btn, true);
    try {
      await api.verifyEmail(email, otp);
      if (password) after(await api.login(email, password));
      else { toast('Email verified — please sign in.'); renderAuth('login'); }
    } catch (ex) { busy(btn, false); err.textContent = ex.message; }
  });
}

function forgotPane() {
  $('[data-pane]').innerHTML = `
    <form style="display:grid;gap:14px" data-forgot-form novalidate>
      <h2 class="h2" style="font-size:28px">Reset password</h2>
      <p class="muted" style="margin:0">Enter your email and we'll send a reset link.</p>
      <label class="field"><span>Email</span><input class="input" type="email" name="email" required></label>
      <p class="form-error" data-err></p><p data-ok class="muted"></p>
      <button class="btn btn--block">Send reset link</button>
      <a class="linkish" data-back style="justify-self:center">Back to sign in</a>
    </form>`;
  $('[data-back]').addEventListener('click', () => loginPane());
  $('[data-forgot-form]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('button.btn', e.target);
    if (!e.target.checkValidity()) { $('[data-err]').textContent = 'Enter a valid email.'; return; }
    busy(btn, true);
    try { const r = await api.requestReset(e.target.email.value.trim()); $('[data-ok]').textContent = r?.message || 'If that email is registered, a reset link is on its way.'; }
    catch (ex) { $('[data-err]').textContent = ex.message; }
    finally { busy(btn, false); }
  });
}

function wireOtpBoxes(form) {
  const boxes = $$('.otp input', form);
  boxes.forEach((b, i) => {
    b.addEventListener('input', () => { b.value = b.value.replace(/\D/g, '').slice(-1); if (b.value && boxes[i + 1]) boxes[i + 1].focus(); });
    b.addEventListener('keydown', (e) => { if (e.key === 'Backspace' && !b.value && boxes[i - 1]) boxes[i - 1].focus(); });
    b.addEventListener('paste', (e) => {
      const digits = (e.clipboardData.getData('text').match(/\d/g) || []).slice(0, 6);
      if (digits.length) { e.preventDefault(); digits.forEach((d, j) => boxes[j] && (boxes[j].value = d)); boxes[Math.min(digits.length, 5)].focus(); }
    });
  });
}

// ------------------------------------------------------------------ signed-in account
function renderAccount(u) {
  const tabs = [['orders', 'My orders', icon.box], ['profile', 'Profile', icon.user], ['security', 'Security', icon.shield]];
  root.innerHTML = `<div class="wrap">
    <div class="page-head"><span class="eyebrow">Account</span><h1 class="h1">Hey ${esc(u.name?.split(' ')[0] || 'there')}</h1></div>
    <div class="account">
      <nav class="side-nav">${tabs.map(([k, l, i]) => `<button data-sec="${k}">${i}${l}</button>`).join('')}
        ${u.role === 'admin' ? `<a class="btn btn--violet btn--sm" href="admin.html" style="margin-top:8px">Open admin</a>` : ''}
        <button data-logout>${icon.logout}Sign out</button></nav>
      <section data-sec-body></section>
    </div></div>`;
  $('[data-logout]').addEventListener('click', async () => { await session.logout(); toast('Signed out'); renderAuth('login'); });
  const show = (k) => {
    $$('[data-sec]').forEach((b) => b.classList.toggle('is-on', b.dataset.sec === k));
    history.replaceState(null, '', `#${k}`);
    ({ orders: ordersSec, profile: profileSec, security: securitySec })[k](u);
  };
  $$('[data-sec]').forEach((b) => b.addEventListener('click', () => show(b.dataset.sec)));
  show(tabs.some(([k]) => `#${k}` === location.hash) ? location.hash.slice(1) : 'orders');
}

async function ordersSec() {
  const body = $('[data-sec-body]');
  body.innerHTML = '<div class="skeleton" style="height:160px"></div>';
  let orders = [];
  try { orders = await api.orders(); } catch (ex) { body.innerHTML = `<p class="form-error">${esc(ex.message)}</p>`; return; }
  if (!orders.length) { body.innerHTML = `<div class="empty">${icon.box}<b>No orders yet</b><a class="btn" href="shop.html">Start shopping</a></div>`; return; }
  body.innerHTML = `<div style="display:grid;gap:14px">${orders.map((o) => {
    const st = String(o.status || 'placed').toLowerCase();
    const canCancel = ['placed', 'processing', 'confirmed', 'pending'].includes(st) && o.payment_status !== 'paid';
    return `<div class="order-card">
      <div class="order-card__head"><div><b>${esc(o.order_id)}</b><div class="muted" style="font-size:12.5px">${fmtDate(o.created_at)} · ${inr(o.total ?? o.subtotal)} · ${o.payment_method === 'cod' || o.payment_status === 'cod_pending' ? 'Cash on delivery' : 'Paid online'}</div></div>
        <span class="status status--${esc(st)}">${esc(st)}</span></div>
      <div class="order-card__items">${(o.items || []).slice(0, 5).map((i) => `<img src="${img(i.image)}" alt="${esc(i.name)}" title="${esc(i.name)} · ${esc(i.size)} × ${i.qty}">`).join('')}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn btn--sm" href="order.html?id=${encodeURIComponent(o.order_id)}">Track</a>
        ${canCancel ? `<button class="btn btn--ghost btn--sm" data-cancel="${esc(o.order_id)}">Cancel order</button>` : ''}</div></div>`;
  }).join('')}</div>`;
  $$('[data-cancel]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm(`Cancel order ${b.dataset.cancel}? This can't be undone.`)) return;
    busy(b, true);
    try { await api.cancelOrder(b.dataset.cancel); toast('Order cancelled'); ordersSec(); } catch (ex) { busy(b, false); toast(ex.message, { type: 'error' }); }
  }));
}

function profileSec(u) {
  $('[data-sec-body]').innerHTML = `<form class="panel" data-prof>
    <div class="form-grid">
      <label class="field"><span>Name</span><input class="input" name="name" value="${esc(u.name || '')}" required minlength="2"></label>
      <label class="field"><span>Email</span><input class="input" value="${esc(u.email || '')}" disabled></label>
      <label class="field"><span>Mobile</span><input class="input" name="phone" value="${esc(u.phone || '')}" inputmode="tel"></label>
      <label class="field"><span>Gender</span><select class="select" name="gender">${['', 'Male', 'Female', 'Other', 'Prefer not to say'].map((g) => `<option ${String(u.gender || '').toLowerCase() === g.toLowerCase() ? 'selected' : ''} value="${g}">${g || 'Select'}</option>`).join('')}</select></label>
    </div><p class="form-error" data-err></p><button class="btn">Save changes</button></form>`;
  $('[data-prof]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('button', e.target); busy(btn, true);
    try { const r = await api.updateProfile(Object.fromEntries(new FormData(e.target))); if (r?.user) session.set(r.user); toast('Profile saved'); }
    catch (ex) { $('[data-err]').textContent = ex.message; } finally { busy(btn, false); }
  });
}

function securitySec() {
  $('[data-sec-body]').innerHTML = `<form class="panel" data-pw>
    <h2 class="h3">Change password</h2>
    <label class="field"><span>Current password</span><input class="input" type="password" name="current_password" required autocomplete="current-password"></label>
    <label class="field"><span>New password</span><input class="input" type="password" name="new_password" required minlength="8" autocomplete="new-password"></label>
    <p class="form-error" data-err></p><button class="btn">Update password</button></form>`;
  $('[data-pw]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('button', e.target); busy(btn, true);
    try { const f = Object.fromEntries(new FormData(e.target)); const r = await api.changePassword({ ...f, confirm_password: f.new_password }); e.target.reset(); toast(r?.message || 'Password updated'); }
    catch (ex) { $('[data-err]').textContent = ex.message; } finally { busy(btn, false); }
  });
}
