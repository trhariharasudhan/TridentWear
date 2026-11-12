import { mountChrome, $, esc, icon, inr, lineHtml, toast, busy, productCard } from '../ui.js';
import { cart, getProducts } from '../store.js';
import { api } from '../api.js';

await mountChrome({ page: 'cart' });
const root = $('[data-cart]');
const COUPON_KEY = 'tw_coupon';

async function render() {
  const { lines, subtotal, savings } = await cart.detailed();
  if (!lines.length) {
    const picks = (await getProducts()).filter((p) => p.featured).slice(0, 4);
    root.style.display = 'block';
    root.innerHTML = `<div class="empty">${icon.bag}<h2 class="h2">Your bag is empty</h2><p class="muted">Start with a heavyweight essential.</p><a class="btn" href="shop.html">Shop now</a></div>
      <div class="grid" style="margin-top:30px">${picks.map((p) => productCard(p)).join('')}</div>`;
    return;
  }
  const coupon = JSON.parse(sessionStorage.getItem(COUPON_KEY) || 'null');
  const discount = coupon ? Math.round(subtotal * coupon.discount_pct) / 100 : 0;
  root.innerHTML = `
    <section>${lines.map(lineHtml).join('')}
      <a class="linkish" href="shop.html" style="display:inline-block;margin-top:18px">← Continue shopping</a></section>
    <aside class="summary">
      <h2 class="h3">Order summary</h2>
      <div class="coupon"><label class="sr-only" for="coupon">Coupon</label><input class="input" id="coupon" placeholder="Coupon code" value="${esc(coupon?.code || '')}"><button class="btn btn--sm" data-apply>${coupon ? 'Remove' : 'Apply'}</button></div>
      <p class="muted" style="margin:-8px 0 0;font-size:12.5px">${coupon ? `<b style="color:var(--ok)">${esc(coupon.code)}</b> applied — ${coupon.discount_pct}% off` : 'New here? Try <b>TRIDENTFIRST</b> for 20% off.'}</p>
      <div class="totals">
        <div><span>Subtotal (${cart.count()} items)</span><span>${inr(subtotal)}</span></div>
        ${savings ? `<div style="color:var(--ok)"><span>MRP savings</span><span>−${inr(savings)}</span></div>` : ''}
        ${discount ? `<div style="color:var(--ok)"><span>Coupon</span><span>−${inr(discount)}</span></div>` : ''}
        <div><span>Shipping</span><span>Free</span></div>
        <div class="grand"><span>Total</span><span>${inr(subtotal - discount)}</span></div>
      </div>
      <a class="btn btn--block" href="checkout.html">Checkout securely</a>
      <div class="secure-note">${icon.shield} Payments secured by Razorpay · COD available</div>
    </aside>`;
  $('[data-apply]').addEventListener('click', async (e) => {
    if (coupon) { sessionStorage.removeItem(COUPON_KEY); render(); return; }
    const code = $('#coupon').value.trim().toUpperCase();
    if (!code) return;
    busy(e.currentTarget, true);
    try {
      const r = await api.applyCoupon(code, subtotal, cart.asOrderItems());
      sessionStorage.setItem(COUPON_KEY, JSON.stringify({ code: r.code || code, discount_pct: r.discount_pct ?? r.discount ?? 0 }));
      toast(`${code} applied`); render();
    } catch (ex) { toast(ex.message, { type: 'error' }); busy(e.currentTarget, false); }
  });
}
addEventListener('tw:cart', render);
render();
