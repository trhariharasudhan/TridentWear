// Order confirmation + public tracking by order ID.
import { mountChrome, $, esc, icon, params, toast, busy } from '../ui.js';
import { api } from '../api.js';

await mountChrome({ page: 'order' });
const root = $('[data-order]');
const q = params();
const STEPS = ['placed', 'processing', 'shipped', 'delivered'];
const stepIndex = (s) => {
  s = String(s || '').toLowerCase();
  if (s === 'in transit') return 2;
  if (s === 'confirmed' || s === 'packed') return 1;
  return Math.max(0, STEPS.indexOf(s));
};

function lookupForm(msg = '') {
  root.innerHTML = `<div class="page-head"><nav class="crumbs"><a href="index.html">Home</a>/<span>Track order</span></nav><h1 class="h1">Track your order</h1></div>
    <form class="panel" data-track style="max-width:520px"><label class="field"><span>Order ID</span><input class="input" name="id" placeholder="TRD-XXXXXXXX" required pattern="TRD-[A-Za-z0-9]{6,}" style="text-transform:uppercase"></label>
    <p class="form-error">${esc(msg)}</p><button class="btn">Track</button></form>`;
  $('[data-track]').addEventListener('submit', (e) => {
    e.preventDefault();
    const id = new FormData(e.target).get('id').trim().toUpperCase();
    location.search = `?id=${encodeURIComponent(id)}`;
  });
}

async function show(id, fresh) {
  root.innerHTML = '<div class="skeleton" style="height:300px;margin-top:40px"></div>';
  let t;
  try { t = await api.track(id); } catch (ex) { return lookupForm(ex.status === 404 ? `We couldn't find order ${id}.` : ex.message); }
  const status = String(t.status || 'placed').toLowerCase();
  const cancelled = status === 'cancelled';
  const idx = stepIndex(status);
  root.innerHTML = `
    ${fresh ? `<div class="success-hero"><div class="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="m5 12 5 5L20 7"/></svg></div>
      <h1 class="h1">Order confirmed</h1><p class="lead" style="text-align:center">Thank you! We've received your order and will email updates as it moves.</p></div>`
      : `<div class="page-head"><nav class="crumbs"><a href="index.html">Home</a>/<a href="order.html">Track</a>/<span>${esc(id)}</span></nav><h1 class="h1">Order status</h1></div>`}
    <div class="panel">
      <div class="order-card__head"><div><span class="muted">Order ID</span><h2 class="h3" style="margin-top:4px">${esc(id)}</h2></div>
        <span class="status status--${cancelled ? 'cancelled' : status.replace(/\s/g, '')}">${esc(t.status)}</span></div>
      ${cancelled ? '<p class="muted">This order was cancelled. Any prepaid amount will be refunded to the original payment method.</p>'
        : `<div class="timeline">${['Placed', 'Packed', 'Shipped', 'Delivered'].map((l, i) => `<div class="${i <= idx ? 'is-done' : ''}">${l}</div>`).join('')}</div>`}
      <table class="spec-table">
        <tr><td>Courier</td><td>${esc(t.courier || 'Pending allocation')}</td></tr>
        <tr><td>Tracking ID</td><td>${esc(t.tracking_id || 'Will appear once shipped')}</td></tr>
        <tr><td>Estimated delivery</td><td>${esc(t.estimated_delivery || 'Updated after dispatch')}</td></tr>
      </table>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <a class="btn" href="shop.html">Continue shopping</a>
        <a class="btn btn--ghost" href="account.html#orders">My orders</a>
        <button class="btn btn--ghost" data-copy>${icon.share}<span>Copy order ID</span></button>
      </div>
    </div>`;
  $('[data-copy]').addEventListener('click', async () => { try { await navigator.clipboard.writeText(id); toast('Order ID copied'); } catch { toast(id); } });
}

const id = (q.get('id') || '').trim().toUpperCase();
id ? show(id, q.get('new') === '1') : lookupForm();
