// Checkout: address -> payment (Razorpay online or COD) -> verify -> order page.
// Prices are always re-calculated by the backend; the UI total is only a preview.
import { mountChrome, $, $$, esc, icon, inr, img, toast, busy, modal } from '../ui.js';
import { cart, session } from '../store.js';
import { api, getMode } from '../api.js';

await mountChrome({ page: 'checkout' });
const root = $('[data-checkout]');
const COUPON_KEY = 'tw_coupon';
const ADDR_KEY = 'tw_last_address';
const STATES = ['Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Delhi', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jammu and Kashmir', 'Jharkhand', 'Karnataka', 'Kerala', 'Ladakh', 'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Puducherry', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal', 'Andaman and Nicobar Islands', 'Chandigarh', 'Dadra and Nagar Haveli and Daman and Diu', 'Lakshadweep'];

const { lines, subtotal } = await cart.detailed();
if (!lines.length) { location.replace('cart.html'); throw new Error('empty'); }
const user = await session.load();
const coupon = JSON.parse(sessionStorage.getItem(COUPON_KEY) || 'null');
const discount = coupon ? Math.round(subtotal * coupon.discount_pct) / 100 : 0;
const saved = JSON.parse(localStorage.getItem(ADDR_KEY) || 'null') || {};
// signed-in shoppers: fill from their default saved address when nothing was typed on this device
if (user && !saved.address) {
  try {
    const def = (await api.addresses()).find((a) => a.is_default);
    if (def) Object.assign(saved, { address: def.street, address2: def.area, pincode: def.pin, city: def.city, state: def.state });
  } catch { /* fine: form stays empty */ }
}
const v = (k, d = '') => esc(saved[k] ?? d);

root.innerHTML = `
  <form data-form novalidate>
    <div class="co-steps"><span class="is-on">1 Details</span><span class="is-on">2 Payment</span><span>3 Done</span></div>
    ${user ? '' : `<div class="panel" style="flex-direction:row;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap"><span>Have an account? Sign in to track orders easily.</span><a class="btn btn--ghost btn--sm" href="account.html?next=checkout.html">Sign in</a></div>`}
    <div class="panel">
      <h2 class="h3">Contact</h2>
      <div class="form-grid">
        <label class="field"><span>Full name</span><input class="input" name="name" required minlength="2" autocomplete="name" value="${esc(user?.name || saved.name || '')}"></label>
        <label class="field"><span>Mobile number</span><input class="input" name="phone" required inputmode="tel" pattern="[6-9][0-9]{9}" maxlength="10" placeholder="10-digit mobile" autocomplete="tel-national" value="${esc((user?.phone || saved.phone || '').replace(/^\+?91/, ''))}"></label>
        <label class="field full"><span>Email (for order updates)</span><input class="input" name="email" type="email" required autocomplete="email" value="${esc(user?.email && !user.email.endsWith('.demo') ? user.email : saved.email || '')}"></label>
      </div>
    </div>
    <div class="panel">
      <h2 class="h3">Delivery address</h2>
      <div class="form-grid">
        <label class="field full"><span>House / flat, street</span><input class="input" name="address" required minlength="6" autocomplete="address-line1" value="${v('address')}"></label>
        <label class="field full"><span>Area, landmark (optional)</span><input class="input" name="address2" autocomplete="address-line2" value="${v('address2')}"></label>
        <label class="field"><span>Pincode</span><input class="input" name="pincode" required inputmode="numeric" pattern="[1-9][0-9]{5}" maxlength="6" autocomplete="postal-code" value="${v('pincode')}"></label>
        <label class="field"><span>City</span><input class="input" name="city" required minlength="2" autocomplete="address-level2" value="${v('city')}"></label>
        <label class="field full"><span>State</span><select class="select" name="state" required><option value="">Select state</option>${STATES.map((s) => `<option ${saved.state === s ? 'selected' : ''}>${s}</option>`).join('')}</select></label>
      </div>
    </div>
    <div class="panel">
      <h2 class="h3">Payment</h2>
      <div class="pay-opts">
        <label class="pay-opt"><input type="radio" name="method" value="online" checked><div style="flex:1"><b>Pay online</b><small>UPI, cards, netbanking & wallets via Razorpay</small></div><div class="pay-icons"><span>UPI</span><span>VISA</span><span>RUPAY</span></div></label>
        <label class="pay-opt"><input type="radio" name="method" value="cod"><div style="flex:1"><b>Cash on delivery</b><small>Pay in cash or UPI when your order arrives</small></div></label>
      </div>
      <p class="form-error" data-error role="alert"></p>
      <button class="btn btn--violet btn--block" data-place>Place order · ${inr(subtotal - discount)}</button>
      <div class="secure-note">${icon.shield} 256-bit encrypted · We never store card details</div>
    </div>
  </form>
  <aside class="summary">
    <h2 class="h3">In your bag</h2>
    <div style="display:grid;gap:12px">${lines.map((l) => `<div class="mini-line"><div class="line__img"><img src="${img(l.product.image)}" alt=""><em>${l.qty}</em></div><div><b>${esc(l.product.name)}</b><div class="muted" style="font-size:12px">${esc(l.product.base_color)} · ${esc(l.size)}</div></div><b>${inr(l.product.price * l.qty)}</b></div>`).join('')}</div>
    <div class="totals">
      <div><span>Subtotal</span><span>${inr(subtotal)}</span></div>
      ${discount ? `<div style="color:var(--ok)"><span>Coupon ${esc(coupon.code)}</span><span>−${inr(discount)}</span></div>` : ''}
      <div><span>Shipping</span><span>Free</span></div>
      <div class="grand"><span>Total</span><span>${inr(subtotal - discount)}</span></div>
    </div>
    <a class="linkish" href="cart.html">Edit bag</a>
  </aside>`;

const form = $('[data-form]');
const errEl = $('[data-error]');
const placeBtn = $('[data-place]');

function collect() {
  $$('.input, .select', form).forEach((i) => i.classList.toggle('is-invalid', !i.checkValidity()));
  if (!form.checkValidity()) {
    const bad = $(':invalid', form);
    bad?.focus();
    const label = bad?.closest('.field')?.querySelector('span')?.textContent || 'a field';
    throw new Error(`Please check: ${label}.`);
  }
  const f = Object.fromEntries(new FormData(form));
  localStorage.setItem(ADDR_KEY, JSON.stringify(f));
  const addressLine = [f.address, f.address2].filter(Boolean).join(', ');
  return {
    method: f.method,
    order: {
      items: cart.asOrderItems(),
      subtotal,
      coupon_code: coupon?.code || undefined,
      customer: { name: f.name.trim(), email: f.email.trim(), phone: f.phone.trim() },
      shipping: { address: addressLine, city: f.city.trim(), state: f.state, pincode: f.pincode.trim(), country: 'India' },
    },
  };
}

function done(orderId) {
  cart.clear();
  sessionStorage.removeItem(COUPON_KEY);
  location.href = `order.html?id=${encodeURIComponent(orderId)}&new=1`;
}

// Razorpay checkout script is loaded only when needed
function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((res, rej) => {
    const s = document.createElement('script');
    s.src = 'https://checkout.razorpay.com/v1/checkout.js';
    s.onload = res; s.onerror = () => rej(new Error('Could not load Razorpay. Check your connection.'));
    document.head.append(s);
  });
}

// Simulated gateway for demo mode / local dev without Razorpay keys
function mockGateway(pay, order) {
  return new Promise((resolve, reject) => {
    const m = modal(`<div class="paysheet__head"><b>TridentWear · Test payment</b><span>${inr(pay.amount / 100)}</span></div>
      <div class="paysheet__body">
        <div class="paysheet__warn">No real money moves. Razorpay keys aren't configured, so this simulates the gateway so you can test the full flow.</div>
        <label class="pay-opt"><input type="radio" name="mk" checked><div><b>UPI</b><small>success@razorpay</small></div></label>
        <button class="btn btn--violet btn--block" data-ok>Pay ${inr(pay.amount / 100)}</button>
        <button class="btn btn--ghost btn--block" data-fail>Simulate failure</button>
      </div>`, { onClose: () => reject(Object.assign(new Error('Payment cancelled.'), { cancelled: true })) });
    m.el.classList.add('paysheet');
    $('[data-ok]', m.el).addEventListener('click', () => {
      m.close = () => {}; m.el.remove();
      resolve({ razorpay_order_id: pay.razorpay_order_id, razorpay_payment_id: 'pay_mock_' + Date.now(), razorpay_signature: 'mock_signature', order_data: { ...order, test_mode: true } });
    });
    $('[data-fail]', m.el).addEventListener('click', () => { m.el.remove(); reject(new Error('Payment failed at the bank. No money was deducted. Please try again.')); });
  });
}

async function realGateway(pay, order) {
  await loadRazorpay();
  return new Promise((resolve, reject) => {
    const rzp = new window.Razorpay({
      key: pay.key_id, amount: pay.amount, currency: pay.currency || 'INR', order_id: pay.razorpay_order_id,
      name: 'TridentWear', description: `Order ${pay.order_id}`,
      image: new URL('assets/brand/icon-192.png', location.href).href,
      prefill: { name: order.customer.name, email: order.customer.email, contact: order.customer.phone },
      notes: { order_id: pay.order_id },
      theme: { color: '#6244c5' },
      handler: (r) => resolve({ ...r, order_data: order }),
      modal: { ondismiss: () => reject(Object.assign(new Error('Payment window closed. Your bag is still saved.'), { cancelled: true })) },
    });
    rzp.on('payment.failed', (r) => reject(new Error(r?.error?.description || 'Payment failed. Please try another method.')));
    rzp.open();
  });
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errEl.textContent = '';
  let data;
  try { data = collect(); } catch (ex) { errEl.textContent = ex.message; return; }
  busy(placeBtn, true, data.method === 'cod' ? 'Placing order…' : 'Connecting to payment…');
  try {
    if (data.method === 'cod') {
      const r = await api.placeCod({ ...data.order, discount_amount: 0 });
      return done(r.order_id);
    }
    const pay = await api.createPayment(data.order);
    const mock = (await getMode()) === 'demo' || !pay.key_id || pay.key_id.includes('mock');
    const result = await (mock ? mockGateway(pay, data.order) : realGateway(pay, data.order));
    busy(placeBtn, false); busy(placeBtn, true, 'Verifying payment…');
    const v = await api.verifyPayment(result);
    done(v.order_id || pay.order_id);
  } catch (ex) {
    busy(placeBtn, false);
    errEl.textContent = ex.message;
    if (!ex.cancelled) toast(ex.message, { type: 'error', timeout: 5000 });
  }
});
