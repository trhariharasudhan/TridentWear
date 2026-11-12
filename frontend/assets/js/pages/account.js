import { mountChrome, $, $$, esc, icon, inr, img, toast, busy, params, fmtDate, modal, productCard } from '../ui.js';
import { session, wishlist, getProducts } from '../store.js';
import { api, getMode } from '../api.js';

await mountChrome({ page: 'account' });
const root = $('[data-account]');
const next = params().get('next');
const safeNext = next && /^[a-z0-9-]+\.html(\?[^#]*)?$/i.test(next) ? next : null; // only same-site pages

const user = await session.load();

// ------------------------------------------------------------------ auth screens
function shell(inner) {
  root.innerHTML = `<div class="auth">
    <div class="auth__art"><div>
      <h1 class="h1" style="max-width:12ch">Join the Trident list</h1>
      <p style="color:#c5c8d3;max-width:36ch">Track orders, save addresses and fit checks, get early access to drops, and take 20% off your first order with TRIDENTFIRST.</p></div>
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
const LOOKS_KEY = 'tw_looks';
const SIZE_KEY = 'tw_size';
const readLS = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
const initials = (n) => String(n || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
const STAGES = ['Placed', 'Confirmed', 'Shipped', 'Delivered'];
const stageOf = (st) => ({ placed: 0, pending: 0, cod_pending: 0, paid: 1, confirmed: 1, processing: 1, shipped: 2, out_for_delivery: 2, delivered: 3 }[st] ?? 0);

async function renderAccount(u) {
  const tabs = [
    ['orders', 'Orders', icon.box], ['saved', 'Saved', icon.heart], ['addresses', 'Addresses', icon.pin], ['size', 'My size', icon.ruler],
    ['looks', 'Fit checks', icon.camera], ['profile', 'Details', icon.user], ['security', 'Security', icon.shield],
  ];
  const since = u.created_at ? new Date(u.created_at).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' }) : '';
  root.innerHTML = `<div class="wrap" style="padding-top:28px">
    <div class="profile-hero">
      <div class="avatar" aria-hidden="true">${esc(initials(u.name))}</div>
      <div><h1 class="sr-only">Your account</h1><h2>Hey ${esc(u.name?.split(' ')[0] || 'there')}</h2><p>${esc(u.email || u.phone || '')}</p></div>
      <div class="tier">${since ? `Member since<b>${esc(since)}</b>` : `TridentWear<b>Member</b>`}</div>
    </div>
    <div class="stat-row" data-stats>
      <button class="stat" data-go="orders"><b data-stat="orders">–</b><span>Orders</span></button>
      <button class="stat" data-go="orders"><b data-stat="transit">–</b><span>On the way</span></button>
      <button class="stat" data-go="saved"><b>${wishlist.ids.length}</b><span>Saved pieces</span></button>
      <button class="stat" data-go="looks"><b>${readLS(LOOKS_KEY, []).length}</b><span>Fit checks</span></button>
    </div>
    <div class="offer-strip" data-offer hidden></div>
    <div class="account">
      <nav class="side-nav" aria-label="Account sections">${tabs.map(([k, l, i]) => `<button data-sec="${k}">${i}${l}</button>`).join('')}
        ${u.role === 'admin' ? `<a class="btn btn--violet btn--sm" href="admin.html" style="margin-top:8px">Open admin</a>` : ''}
        <button data-logout>${icon.logout}Sign out</button></nav>
      <section data-sec-body aria-live="polite"></section>
    </div></div>`;
  $('[data-logout]').addEventListener('click', async () => { await session.logout(); toast('Signed out'); renderAuth('login'); });
  const show = (k) => {
    $$('[data-sec]').forEach((b) => b.classList.toggle('is-on', b.dataset.sec === k));
    history.replaceState(null, '', `#${k}`);
    ({ orders: ordersSec, saved: savedSec, addresses: addressSec, size: sizeSec, looks: looksSec, profile: profileSec, security: securitySec })[k](u);
  };
  $$('[data-sec]').forEach((b) => b.addEventListener('click', () => show(b.dataset.sec)));
  $$('[data-go]').forEach((b) => b.addEventListener('click', () => { show(b.dataset.go); $('.account').scrollIntoView({ behavior: 'smooth', block: 'start' }); }));
  show(tabs.some(([k]) => `#${k}` === location.hash) ? location.hash.slice(1) : 'orders');
  api.orders().then((orders) => {
    $('[data-stat="orders"]').textContent = orders.length;
    const offer = $('[data-offer]');
    offer.hidden = false;
    offer.innerHTML = orders.length
      ? `<div><b>Member perk</b><span>Free shipping and 7-day exchanges on every order. Early access to Drop 02 lands in your inbox.</span></div>`
      : `<div><b>20% off your first order</b><span>Use this code at checkout. It applies automatically to one order.</span></div><button class="offer-code" data-copy="TRIDENTFIRST">TRIDENTFIRST <small>Copy</small></button>`;
    $('[data-copy]', offer)?.addEventListener('click', async (e) => {
      try { await navigator.clipboard.writeText(e.currentTarget.dataset.copy); toast('Code copied'); } catch { toast('Code: TRIDENTFIRST'); }
    });
    $('[data-stat="transit"]').textContent = orders.filter((o) => ['shipped', 'out_for_delivery'].includes(String(o.status).toLowerCase())).length;
  }).catch(() => {});
}

const sec = (title, action = '') => `<header><h3>${title}</h3>${action}</header>`;

async function ordersSec() {
  const body = $('[data-sec-body]');
  body.innerHTML = '<div class="skeleton" style="height:160px"></div>';
  let orders = [];
  try { orders = await api.orders(); } catch (ex) { body.innerHTML = `<p class="form-error">${esc(ex.message)}</p>`; return; }
  if (!orders.length) { body.innerHTML = `<div class="acc-section">${sec('Orders')}<div class="empty">${icon.box}<b>No orders yet</b><p class="muted">When you place an order, you can track it here.</p><a class="btn" href="shop.html">Browse the shop</a></div></div>`; return; }
  body.innerHTML = `<div class="acc-section">${sec('Orders', `<span class="muted">${orders.length} order${orders.length > 1 ? 's' : ''}</span>`)}${orders.map((o) => {
    const st = String(o.status || 'placed').toLowerCase();
    const cancelled = ['cancelled', 'failed'].includes(st);
    const at = stageOf(st);
    const canCancel = ['placed', 'processing', 'confirmed', 'pending'].includes(st) && o.payment_status !== 'paid';
    return `<div class="order-card">
      <div class="order-card__head"><div><b>${esc(o.order_id)}</b><div class="muted" style="font-size:13.5px">${fmtDate(o.created_at)} · ${inr(o.total ?? o.subtotal)} · ${o.payment_method === 'cod' || o.payment_status === 'cod_pending' ? 'Cash on delivery' : 'Paid online'}</div></div>
        <span class="status status--${esc(st)}">${esc(st.replace(/_/g, ' '))}</span></div>
      ${cancelled ? '' : `<div><div class="mini-track" aria-hidden="true">${STAGES.map((_, i) => `<i class="${i <= at ? 'is-done' : ''}"></i>`).join('')}</div>
        <div class="mini-track-labels">${STAGES.map((l, i) => `<span style="${i === at ? 'color:var(--ink);font-weight:600' : ''}">${l}</span>`).join('')}</div></div>`}
      <div class="order-card__items">${(o.items || []).slice(0, 5).map((i) => `<img src="${img(i.image)}" alt="${esc(i.name)}, size ${esc(i.size)}" title="${esc(i.name)} · ${esc(i.size)} × ${i.qty}" loading="lazy">`).join('')}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn btn--sm" href="order.html?id=${encodeURIComponent(o.order_id)}">Track order</a>
        ${canCancel ? `<button class="btn btn--ghost btn--sm" data-cancel="${esc(o.order_id)}">Cancel order</button>` : ''}</div></div>`;
  }).join('')}</div>`;
  $$('[data-cancel]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm(`Cancel order ${b.dataset.cancel}? This can't be undone.`)) return;
    busy(b, true);
    try { await api.cancelOrder(b.dataset.cancel); toast('Order cancelled'); ordersSec(); } catch (ex) { busy(b, false); toast(ex.message, { type: 'error' }); }
  }));
}

// ---- saved pieces (wishlist)
async function savedSec() {
  const body = $('[data-sec-body]');
  const ids = wishlist.ids;
  if (!ids.length) { body.innerHTML = `<div class="acc-section">${sec('Saved pieces')}<div class="empty">${icon.heart}<b>Nothing saved yet</b><p class="muted">Tap the heart on any piece to keep it here.</p><a class="btn" href="shop.html">Browse the shop</a></div></div>`; return; }
  const products = (await getProducts()).filter((p) => ids.includes(p.id));
  body.innerHTML = `<div class="acc-section">${sec('Saved pieces', `<span class="muted">${products.length} saved</span>`)}<div class="grid grid--3">${products.map((p) => productCard(p)).join('')}</div></div>`;
}

// ---- saved addresses
const STATES = ['Andhra Pradesh', 'Assam', 'Bihar', 'Chandigarh', 'Chhattisgarh', 'Delhi', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jammu and Kashmir', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Odisha', 'Puducherry', 'Punjab', 'Rajasthan', 'Tamil Nadu', 'Telangana', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal'];
async function addressSec() {
  const body = $('[data-sec-body]');
  body.innerHTML = '<div class="skeleton" style="height:140px"></div>';
  let list = [];
  try { list = await api.addresses(); } catch (ex) { body.innerHTML = `<p class="form-error">${esc(ex.message)}</p>`; return; }
  body.innerHTML = `<div class="acc-section">${sec('Saved addresses', '<button class="btn btn--sm" data-add-addr>Add address</button>')}
    ${list.length ? `<div class="addr-grid">${list.map((a) => `<div class="addr ${a.is_default ? 'is-default' : ''}">
      ${a.is_default ? '<span class="tag">Default</span>' : ''}<b>${esc(a.label || 'Home')}</b>
      <span>${esc(a.street)}${a.area ? `, ${esc(a.area)}` : ''}</span><span class="muted">${esc(a.city)}, ${esc(a.state)} ${esc(a.pin)}</span>
      <div style="display:flex;gap:14px;margin-top:8px">${a.is_default ? '' : `<button class="linkish" data-default="${esc(a.address_id)}">Make default</button>`}<button class="linkish" style="color:var(--bad)" data-del="${esc(a.address_id)}">Remove</button></div></div>`).join('')}</div>`
      : `<div class="empty">${icon.pin}<b>No saved addresses</b><p class="muted">Save one now and checkout fills it in for you.</p></div>`}</div>`;
  $('[data-add-addr]').addEventListener('click', () => {
    const m = modal(`<h2 class="h3" style="margin-bottom:16px">Add an address</h2><form class="form-grid" data-addr>
      <label class="field"><span>Label</span><select class="select" name="label"><option>Home</option><option>Work</option><option>Other</option></select></label>
      <label class="field"><span>PIN code</span><input class="input" name="pin" required pattern="[1-9][0-9]{5}" inputmode="numeric" maxlength="6"></label>
      <label class="field full"><span>House number and street</span><input class="input" name="street" required minlength="4" autocomplete="address-line1"></label>
      <label class="field full"><span>Area or landmark (optional)</span><input class="input" name="area" autocomplete="address-line2"></label>
      <label class="field"><span>City</span><input class="input" name="city" required autocomplete="address-level2"></label>
      <label class="field"><span>State</span><select class="select" name="state" required><option value="">Select</option>${STATES.map((x) => `<option>${x}</option>`).join('')}</select></label>
      <label class="check full"><input type="checkbox" name="is_default" ${list.length ? '' : 'checked'}> Use as my default address</label>
      <p class="form-error full" data-err></p><button class="btn full">Save address</button></form>`);
    $('[data-addr]', m.el).addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = e.target; if (!f.reportValidity()) return;
      const data = Object.fromEntries(new FormData(f)); data.is_default = !!f.is_default.checked;
      const btn = $('button.btn', f); busy(btn, true);
      try { await api.addAddress(data); m.close(); toast('Address saved'); addressSec(); }
      catch (ex) { $('[data-err]', f).textContent = ex.message; busy(btn, false); }
    });
  });
  $$('[data-default]').forEach((b) => b.addEventListener('click', async () => { await api.updateAddress(b.dataset.default, { is_default: true }); toast('Default address updated'); addressSec(); }));
  $$('[data-del]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Remove this address?')) return;
    try { await api.deleteAddress(b.dataset.del); toast('Address removed'); addressSec(); } catch (ex) { toast(ex.message, { type: 'error' }); }
  }));
}

// ---- size profile (kept on this device; also used to pre-select sizes)
const sizeFor = (h, w) => {
  const order = ['S', 'M', 'L', 'XL', 'XXL'];
  let i = w < 58 ? 0 : w < 68 ? 1 : w < 78 ? 2 : w < 90 ? 3 : 4;
  if (h >= 183 && i < 4) i += 1; // tall frames need the extra length
  return order[i];
};
function sizeSec() {
  const saved = readLS(SIZE_KEY, {});
  const body = $('[data-sec-body]');
  const result = (s) => (s?.size ? `<div class="size-result"><span>Your TridentWear size</span><b>${esc(s.size)}</b>
      <span style="color:#b4b8c6">Based on ${esc(s.height)} cm and ${esc(s.weight)} kg. Oversized pieces are cut roomy, so take this size for the intended fit, or one smaller for a closer fit.</span></div>`
    : `<div class="size-result"><span>Your TridentWear size</span><b>?</b><span style="color:#b4b8c6">Add your height and weight to get an estimate.</span></div>`);
  body.innerHTML = `<div class="acc-section">${sec('My size')}<div class="size-profile">
    <form class="panel" data-size-form>
      <label class="field"><span>Height (cm)</span><input class="input" name="height" type="number" min="140" max="210" required value="${esc(saved.height || '')}"></label>
      <label class="field"><span>Weight (kg)</span><input class="input" name="weight" type="number" min="35" max="160" required value="${esc(saved.weight || '')}"></label>
      <button class="btn">Work out my size</button><p class="muted" style="margin:0;font-size:13.5px">This is an estimate. Each product page also has the full size chart.</p>
    </form><div data-size-out>${result(saved)}</div></div></div>`;
  $('[data-size-form]').addEventListener('submit', (e) => {
    e.preventDefault();
    const h = Number(e.target.height.value), w = Number(e.target.weight.value);
    const s = { height: h, weight: w, size: sizeFor(h, w) };
    try { localStorage.setItem(SIZE_KEY, JSON.stringify(s)); } catch {}
    $('[data-size-out]').innerHTML = result(s);
    toast(`Saved. Your size is ${s.size}.`);
  });
}

// ---- saved fit checks
function looksSec() {
  const looks = readLS(LOOKS_KEY, []);
  const body = $('[data-sec-body]');
  body.innerHTML = `<div class="acc-section">${sec('My fit checks', looks.length ? '<button class="linkish" data-clear-looks>Clear all</button>' : '')}
    ${looks.length ? `<div class="saved-looks">${looks.map((l, i) => `<figure><img src="${l.src}" alt="Fit check of ${esc(l.name)}, size ${esc(l.size)}"><figcaption>
      <a class="btn btn--light btn--sm" href="product.html?id=${l.id}">${esc(l.size)} · Shop</a><a class="icon-btn" style="background:rgba(255,255,255,.85)" href="${l.src}" download="tridentwear-fit-check-${i + 1}.jpg" aria-label="Download">${icon.download}</a></figcaption></figure>`).join('')}</div>`
      : `<div class="empty">${icon.camera}<b>No fit checks yet</b><p class="muted">Take one in Fit Check and it will be saved here on this device.</p><a class="btn" href="tryon.html">Open Fit Check</a></div>`}</div>`;
  $('[data-clear-looks]')?.addEventListener('click', () => { if (!confirm('Delete all saved fit checks from this device?')) return; localStorage.removeItem(LOOKS_KEY); looksSec(); });
}

const PREFS = [
  ['order_updates_email', 'Order updates by email', 'Confirmation, shipping and delivery.'],
  ['order_updates_whatsapp', 'Order updates on WhatsApp', 'Same updates, on your phone.'],
  ['new_drops', 'New drop alerts', 'One email when a new drop goes live.'],
  ['marketing', 'Offers and member codes', 'Occasional discounts. Never more than twice a month.'],
];
async function profileSec(u) {
  const body = $('[data-sec-body]');
  body.innerHTML = '<div class="skeleton" style="height:220px"></div>';
  let prof = {};
  try { prof = await api.profile(); } catch { /* fall back to session copy */ }
  const settings = prof.settings || {};
  body.innerHTML = `<div class="acc-section">${sec('Your details')}<form class="panel" data-prof>
    <div class="form-grid">
      <label class="field"><span>Name</span><input class="input" name="name" value="${esc(u.name || '')}" required minlength="2" autocomplete="name"></label>
      <label class="field"><span>Email</span><input class="input" value="${esc(u.email || '')}" disabled></label>
      <label class="field"><span>Mobile</span><input class="input" name="phone" value="${esc(u.phone || '')}" inputmode="tel" autocomplete="tel"></label>
      <label class="field"><span>Birthday <small class="muted">(for a birthday code)</small></span><input class="input" type="date" name="birthday" value="${esc(prof.birthday || '')}" max="${new Date().toISOString().slice(0, 10)}"></label>
      <label class="field"><span>Gender</span><select class="select" name="gender">${['', 'Male', 'Female', 'Other', 'Prefer not to say'].map((g) => `<option ${String(u.gender || '').toLowerCase() === g.toLowerCase() ? 'selected' : ''} value="${g}">${g || 'Select'}</option>`).join('')}</select></label>
    </div><p class="form-error" data-err></p><button class="btn">Save changes</button></form>
    <form class="panel" data-prefs><h2 class="h3">Notifications</h2>
      ${PREFS.map(([k, l, d]) => `<label class="switch"><span><b>${l}</b><small class="muted">${d}</small></span><input type="checkbox" role="switch" name="${k}" ${(settings[k] ?? (k === 'order_updates_email' || k === 'new_drops')) ? 'checked' : ''}><i aria-hidden="true"></i></label>`).join('')}
    </form></div>`;
  $('[data-prof]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('button', e.target); busy(btn, true);
    try { const r = await api.updateProfile(Object.fromEntries(new FormData(e.target))); if (r?.user || r?.profile?.user) session.set(r.user || r.profile.user); toast('Details saved'); }
    catch (ex) { $('[data-err]').textContent = ex.message; } finally { busy(btn, false); }
  });
  $('[data-prefs]').addEventListener('change', async (e) => {
    const f = e.currentTarget;
    const next = Object.fromEntries(PREFS.map(([k]) => [k, f[k].checked]));
    try { await api.updateProfile({ settings: next }); toast('Preferences saved'); }
    catch (ex) { e.target.checked = !e.target.checked; toast(ex.message, { type: 'error' }); }
  });
}

function securitySec(u) {
  $('[data-sec-body]').innerHTML = `<div class="acc-section">${sec('Security')}<form class="panel" data-pw>
    <h2 class="h3">Change password</h2>
    <label class="field"><span>Current password</span><input class="input" type="password" name="current_password" required autocomplete="current-password"></label>
    <label class="field"><span>New password</span><input class="input" type="password" name="new_password" required minlength="8" autocomplete="new-password"></label>
    <p class="form-error" data-err></p><button class="btn">Update password</button></form>
    <div class="panel danger"><h2 class="h3">Delete account</h2><p class="muted" style="margin:0">This removes your name, email, phone, addresses and preferences. Past orders stay on record only for invoices and tax. This can't be undone.</p>
      <button class="btn btn--ghost" data-delete-acc style="justify-self:start;color:var(--bad);border-color:currentColor">Delete my account</button></div></div>`;
  $('[data-pw]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('button', e.target); busy(btn, true);
    try { const f = Object.fromEntries(new FormData(e.target)); const r = await api.changePassword({ ...f, confirm_password: f.new_password }); e.target.reset(); toast(r?.message || 'Password updated'); }
    catch (ex) { $('[data-err]').textContent = ex.message; } finally { busy(btn, false); }
  });
  $('[data-delete-acc]').addEventListener('click', () => {
    if (u?.role === 'admin') { toast("Admin accounts can't be deleted here", { type: 'error' }); return; }
    const m = modal(`<h2 class="h3" style="margin-bottom:10px">Delete your account?</h2><p class="muted">Enter your password and type DELETE to confirm.</p>
      <form data-del-form style="display:grid;gap:12px"><input class="input" type="password" name="password" placeholder="Password" required autocomplete="current-password">
      <input class="input" name="confirm" placeholder="Type DELETE" required autocomplete="off"><p class="form-error" data-err></p>
      <button class="btn" style="--bg:var(--bad)">Delete my account</button></form>`);
    $('[data-del-form]', m.el).addEventListener('submit', async (e) => {
      e.preventDefault(); const btn = $('button', e.target); busy(btn, true);
      try { const r = await api.deleteAccount(Object.fromEntries(new FormData(e.target))); m.close(); session.set(null); toast(r?.message || 'Account deleted'); setTimeout(() => (location.href = 'index.html'), 1200); }
      catch (ex) { $('[data-err]', e.target).textContent = ex.message; busy(btn, false); }
    });
  });
}

// First render runs last: renderAccount() uses constants declared further up this module
// (calling it before them threw a TDZ error and left signed-in visitors with a blank page).
user ? renderAccount(user) : renderAuth(location.hash === '#register' ? 'register' : 'login');
