import { mountChrome, $, $$, productCard, params, esc, icon, inr, img, gallery, discountPct, modal, toast, busy, fmtDate, reveal } from '../ui.js';
import { getProduct, getProducts, siblings, cart, wishlist, session } from '../store.js';
import { api } from '../api.js';
import { CONFIG } from '../config.js';

await mountChrome({ page: 'shop' });
const id = Number(params().get('id'));
const root = $('[data-pdp]');

let p;
try { p = await getProduct(id); if (!p) throw new Error('Product not found'); } catch {
  root.innerHTML = `<div class="empty" style="grid-column:1/-1">${icon.search}<b>We couldn't find that product.</b><a class="btn" href="shop.html">Back to shop</a></div>`;
  $('[data-reviews-wrap]').hidden = true;
  throw new Error('product missing');
}

// size charts (inches) — edit to match your production spec sheets
const CHARTS = {
  Oversized: { chest: [44, 46, 48, 50, 52], length: [27, 28, 29, 30, 31], shoulder: [20.5, 21.5, 22.5, 23.5, 24.5] },
  Regular: { chest: [38, 40, 42, 44, 46], length: [26, 27, 28, 29, 30], shoulder: [16.5, 17.5, 18.5, 19.5, 20.5] },
  Slim: { chest: [37, 39, 41, 43, 45], length: [28, 29, 30, 31, 32], shoulder: [16.5, 17, 18, 19, 20] },
  Relaxed: { chest: [42, 44, 46, 48, 50], length: [28, 29, 30, 31, 32], shoulder: [18, 19, 20, 21, 22] },
};
const SIZES = ['S', 'M', 'L', 'XL', 'XXL'];
const state = { size: '', qty: 1, view: 0, recommended: '' };
const colorways = await siblings(p);
const pics = gallery(p);
const off = discountPct(p);

document.title = `${p.name} — ${p.base_color} · TridentWear`;
$('[data-crumbs]').insertAdjacentHTML('beforeend', `/<a href="shop.html?cat=${p.category}">${p.category === 'shirt' ? 'Shirts' : 'T-Shirts'}</a>/<span>${esc(p.name)}</span>`);

root.innerHTML = `
  <div class="gallery">
    <div class="thumbs">${pics.map((src, i) => `<button class="${i === 0 ? 'is-on' : ''}" data-view="${i}" aria-label="View ${i ? 'back' : 'front'}"><img src="${src}" alt=""></button>`).join('')}</div>
    <div class="stage" data-stage><img src="${pics[0]}" alt="${esc(p.name)} in ${esc(p.base_color)}" data-main>
      <a class="btn btn--light btn--sm stage__tryon" href="tryon.html?id=${p.id}">${icon.camera}<span>Try it on</span></a></div>
  </div>
  <div class="info">
    <div style="display:grid;gap:10px">
      <div style="display:flex;gap:8px;flex-wrap:wrap">${p.tag ? `<span class="tag tag--violet">${esc(p.tag)}</span>` : ''}<span class="tag tag--line">${esc(p.fit_type || '')} fit</span><span class="tag tag--line">${esc(String(p.gsm || ''))} GSM</span></div>
      <h1 class="h1" style="font-size:clamp(30px,3.6vw,46px)">${esc(p.name)}</h1>
      <div class="info__price"><span class="price">${inr(p.price)}</span>${off ? `<span class="mrp">MRP ${inr(p.mrp)}</span><span class="off">${off}% off</span>` : ''}<div class="muted" style="font-size:12px">Inclusive of all taxes · Free shipping</div></div>
    </div>
    <p class="muted" style="margin:0">${esc(p.description)}</p>
    <div>
      <div class="opt-label"><span>Colour · <b>${esc(p.base_color)}</b></span></div>
      <div class="color-opts">${colorways.map((c) => `<a class="color-opt ${c.id === p.id ? 'is-on' : ''}" href="product.html?id=${c.id}" title="${esc(c.base_color)}" aria-label="${esc(c.base_color)}"><span style="background:${esc(c.color_hex || '#ccc')}"></span></a>`).join('')}</div>
    </div>
    <div>
      <div class="opt-label"><span>Size <b data-size-label></b></span><span style="display:flex;gap:14px"><a data-finder>${icon.spark.replace('<svg', '<svg style="width:14px;height:14px;display:inline;vertical-align:-2px"')} Find my size</a><a data-guide>Size guide</a></span></div>
      <div class="size-opts">${SIZES.map((s) => `<button class="size-opt" data-size="${s}" ${(p.sizes || []).includes(s) ? '' : 'disabled style="opacity:.35;text-decoration:line-through"'}>${s}</button>`).join('')}</div>
      <p class="form-error" data-size-error></p>
    </div>
    <div class="buy-row">
      <div class="qty"><button data-q="-1" aria-label="Decrease">−</button><input value="1" readonly aria-label="Quantity" data-qty><button data-q="1" aria-label="Increase">+</button></div>
      <button class="btn" data-add ${p.stock <= 0 ? 'disabled' : ''}>${p.stock <= 0 ? 'Sold out' : 'Add to bag'}</button>
      <button class="icon-btn card__wish ${wishlist.has(p.id) ? 'is-on' : ''}" style="position:static;border:1.5px solid var(--line);width:50px;height:50px" data-wish="${p.id}" aria-label="Save to wishlist">${icon.heart}</button>
    </div>
    ${p.stock > 0 ? `<button class="btn btn--violet btn--block" data-buy>Buy now</button>` : ''}
    ${p.stock > 0 && p.stock <= 10 ? `<p style="margin:0;color:var(--warn);font-weight:600;font-size:13px">Only ${p.stock} left in stock</p>` : ''}
    <div class="ai-strip">${icon.camera}<p><b>Not sure how it looks?</b><br>See it on you live with AI Fit Check — no upload, all on your phone.</p><a class="btn btn--sm" href="tryon.html?id=${p.id}">Try on</a></div>
    <div class="perks"><div>${icon.truck}Free shipping</div><div>${icon.swap}${CONFIG.returnDays}-day exchange</div><div>${icon.cash}COD available</div></div>
    <div>
      <details class="acc" open><summary>Details</summary><div class="acc__body"><table class="spec-table">
        ${[['Fabric', p.fabric], ['Weight', p.gsm ? `${p.gsm} GSM` : ''], ['Fit', p.fit_type], ['Neck / collar', p.neck_type], ['Branding', (p.print_method || []).length ? p.print_method.join(' + ') + ' Trident mark' : ''], ['Style code', p.style_code], ['Made in', 'India']]
          .filter(([, v]) => v).map(([k, v]) => `<tr><td>${k}</td><td>${esc(v)}</td></tr>`).join('')}</table></div></details>
      <details class="acc"><summary>Wash care</summary><div class="acc__body"><ul style="margin:0;padding-left:18px">${(p.wash_care || []).map((w) => `<li>${esc(w)}</li>`).join('')}</ul></div></details>
      <details class="acc"><summary>Delivery & returns</summary><div class="acc__body">
        <div class="pin-check"><input class="input" inputmode="numeric" maxlength="6" placeholder="Enter pincode" data-pin><button class="btn btn--sm" data-pin-btn>Check</button></div>
        <p data-pin-out class="muted" style="margin:10px 0 0">Free shipping across India. Dispatch in 1–2 business days.</p>
        <p class="muted" style="margin:6px 0 0">Easy ${CONFIG.returnDays}-day size exchange. <a class="linkish" href="policies.html#returns">Policy</a></p></div></details>
    </div>
  </div>`;

// ---- gallery
const main = $('[data-main]');
$$('[data-view]').forEach((b) => b.addEventListener('click', () => {
  $$('[data-view]').forEach((x) => x.classList.remove('is-on')); b.classList.add('is-on');
  main.src = pics[Number(b.dataset.view)];
}));
const stage = $('[data-stage]');
stage.addEventListener('click', (e) => {
  if (e.target.closest('a')) return;
  stage.classList.toggle('is-zoom');
  if (!stage.classList.contains('is-zoom')) main.style.transformOrigin = '';
});
stage.addEventListener('mousemove', (e) => {
  if (!stage.classList.contains('is-zoom')) return;
  const r = stage.getBoundingClientRect();
  main.style.transformOrigin = `${((e.clientX - r.left) / r.width) * 100}% ${((e.clientY - r.top) / r.height) * 100}%`;
});

// ---- size + qty
function pickSize(s) {
  state.size = s;
  $$('[data-size]').forEach((b) => b.classList.toggle('is-on', b.dataset.size === s));
  $('[data-size-label]').textContent = s ? `· ${s}` : '';
  $('[data-size-error]').textContent = '';
}
$$('[data-size]').forEach((b) => b.addEventListener('click', () => pickSize(b.dataset.size)));
$$('[data-q]').forEach((b) => b.addEventListener('click', () => {
  state.qty = Math.max(1, Math.min(10, state.qty + Number(b.dataset.q)));
  $('[data-qty]').value = state.qty;
}));

function add() {
  if (!state.size) {
    $('[data-size-error]').textContent = 'Please choose a size.';
    $('.size-opts').animate([{ transform: 'translateX(0)' }, { transform: 'translateX(-6px)' }, { transform: 'translateX(6px)' }, { transform: 'translateX(0)' }], { duration: 300 });
    return false;
  }
  cart.add(p.id, state.size, state.qty);
  toast(`Added ${p.name} (${state.size})`, { image: img(p.image), link: { href: 'cart.html', label: 'View bag' } });
  return true;
}
$('[data-add]')?.addEventListener('click', add);
$('[data-buy]')?.addEventListener('click', () => { if (add()) location.href = 'checkout.html'; });

// mobile sticky buy bar
const sticky = $('[data-sticky]');
if (p.stock > 0) {
  sticky.hidden = false;
  $('[data-sticky-add]').addEventListener('click', () => { if (!add()) $('.size-opts').scrollIntoView({ behavior: 'smooth', block: 'center' }); });
  $('[data-sticky-try]').addEventListener('click', () => (location.href = `tryon.html?id=${p.id}`));
}

// ---- size guide
const chart = CHARTS[p.fit_type] || CHARTS.Regular;
$('[data-guide]').addEventListener('click', () => modal(`
  <h3 class="h3" style="margin-bottom:6px">Size guide · ${esc(p.fit_type)} fit</h3>
  <p class="muted" style="margin-top:0">Garment measurements in inches. ${p.fit_type === 'Oversized' ? 'Cut roomy on purpose — size down for a regular look.' : ''}</p>
  <table class="size-table"><tr><th>Size</th>${SIZES.map((s) => `<th>${s}</th>`).join('')}</tr>
  ${Object.entries(chart).map(([k, row]) => `<tr><td style="text-transform:capitalize;font-weight:600">${k}</td>${row.map((v) => `<td>${v}</td>`).join('')}</tr>`).join('')}</table>`));

// ---- AI size finder (heuristic estimate)
function recommend(h, w, pref) {
  let i = w < 58 ? 0 : w < 68 ? 1 : w < 78 ? 2 : w < 90 ? 3 : 4;
  if (h >= 185 && i < 4) i++;
  if (h <= 160 && w < 70 && i > 0) i--;
  if (pref === 'relaxed' && p.fit_type !== 'Oversized') i++;
  if (pref === 'snug') i--;
  if (pref === 'regular' && p.fit_type === 'Oversized') i--;
  return SIZES[Math.max(0, Math.min(4, i))];
}
$('[data-finder]').addEventListener('click', () => {
  const m = modal(`
    <h3 class="h3">Find my size</h3><p class="muted" style="margin-top:4px">Tell us a little about you and we'll suggest a size for this ${esc(p.fit_type.toLowerCase())} fit.</p>
    <form class="form-grid" data-sf>
      <label class="field"><span>Height (cm)</span><input class="input" name="h" type="number" min="140" max="210" required value="172"></label>
      <label class="field"><span>Weight (kg)</span><input class="input" name="w" type="number" min="40" max="150" required value="68"></label>
      <label class="field full"><span>How do you like it to fit?</span><select class="select" name="pref"><option value="snug">Snug</option><option value="regular" selected>Regular</option><option value="relaxed">Relaxed / roomy</option></select></label>
      <button class="btn full">Get my size</button></form><div data-sf-out style="margin-top:16px"></div>`);
  $('[data-sf]', m.el).addEventListener('submit', (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const s = recommend(Number(f.get('h')), Number(f.get('w')), f.get('pref'));
    $('[data-sf-out]', m.el).innerHTML = `<div class="ai-strip">${icon.spark}<p>We recommend <b style="font-size:20px">${s}</b><br><small class="muted">An estimate based on typical fits — check the size guide if you're between sizes.</small></p><button class="btn btn--sm" data-use="${s}">Select ${s}</button></div>`;
    $('[data-use]', m.el).addEventListener('click', () => { pickSize(s); $$('[data-size]').forEach((b) => b.classList.toggle('is-rec', b.dataset.size === s)); m.close(); });
  });
});

// ---- pincode check (format only; courier serviceability API can be wired later)
$('[data-pin-btn]').addEventListener('click', () => {
  const v = $('[data-pin]').value.trim();
  const out = $('[data-pin-out]');
  if (!/^[1-9][0-9]{5}$/.test(v)) { out.textContent = 'Enter a valid 6-digit pincode.'; out.style.color = 'var(--bad)'; return; }
  const metro = /^(11|40|56|60|70|50)/.test(v);
  const eta = new Date(Date.now() + (metro ? 4 : 7) * 864e5).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
  out.style.color = 'var(--ok)';
  out.textContent = `Delivers to ${v} by around ${eta}. Free shipping · COD available.`;
});

// ---- reviews
async function loadReviews() {
  const wrap = $('[data-reviews]');
  try {
    const r = await api.reviews(p.id);
    $('[data-review-title]').textContent = r.count ? `${r.average} ★ · ${r.count} review${r.count > 1 ? 's' : ''}` : 'Customer reviews';
    wrap.innerHTML = r.count ? r.reviews.slice(0, 8).map((x) => `<div class="review"><div class="stars">${'★'.repeat(x.rating)}${'☆'.repeat(5 - x.rating)}</div><p style="margin:8px 0">${esc(x.review || x.comment || '')}</p><small class="muted">${esc(x.user_name || x.name || 'Verified buyer')} · ${fmtDate(x.created_at)}</small></div>`).join('')
      : `<div class="review"><b>No reviews yet.</b><p class="muted" style="margin:6px 0 0">This piece just dropped — be the first to review it after your order arrives.</p></div>`;
  } catch { wrap.innerHTML = ''; }
}
loadReviews();
$('[data-write-review]').addEventListener('click', async () => {
  const user = await session.load();
  if (!user) { location.href = `account.html?next=${encodeURIComponent(location.pathname.split('/').pop() + location.search)}`; return; }
  const m = modal(`<h3 class="h3">Review ${esc(p.name)}</h3>
    <form style="display:grid;gap:14px;margin-top:14px" data-rv>
      <div class="star-input">${[5, 4, 3, 2, 1].map((n) => `<input type="radio" name="rating" id="r${n}" value="${n}" ${n === 5 ? 'checked' : ''}><label for="r${n}">★</label>`).join('')}</div>
      <textarea class="textarea" name="review" required minlength="10" placeholder="How was the fit, fabric and feel?"></textarea>
      <p class="form-error" data-rv-err></p><button class="btn">Submit review</button></form>`);
  $('[data-rv]', m.el).addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target); const btn = $('button.btn', e.target);
    busy(btn, true);
    try { const r = await api.addReview({ product_id: p.id, rating: Number(f.get('rating')), review: f.get('review') }); m.close(); toast(r?.message || 'Thanks! Your review is awaiting moderation.'); }
    catch (ex) { $('[data-rv-err]', m.el).textContent = ex.message; busy(btn, false); }
  });
});

// ---- related
const all = await getProducts();
const related = all.filter((x) => x.id !== p.id && x.style_code !== p.style_code).sort((a, b) => (b.category === p.category) - (a.category === p.category) || b.featured - a.featured).slice(0, 8);
$('[data-related]').innerHTML = related.map((x) => productCard(x)).join('');

// SEO: product structured data
const ld = document.createElement('script');
ld.type = 'application/ld+json';
ld.textContent = JSON.stringify({ '@context': 'https://schema.org', '@type': 'Product', name: `${p.name} — ${p.base_color}`, image: pics.map((s) => new URL(s, location.href).href), description: p.description, sku: `${p.style_code || 'TW'}-${p.id}`, brand: { '@type': 'Brand', name: 'TridentWear' }, offers: { '@type': 'Offer', priceCurrency: 'INR', price: p.price, availability: p.stock > 0 ? 'https://schema.org/InStock' : 'https://schema.org/OutOfStock' } }).replace(/</g, '\\u003c');
document.head.append(ld);
reveal();
