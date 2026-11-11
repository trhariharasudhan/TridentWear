// Admin dashboard: analytics, products, orders, customers, coupons, reviews.
// All data calls hit /api/v1/admin/* (or the demo adapter). The server enforces admin role.
import { $, $$, esc, icon, inr, img, toast, busy, modal, fmtDate, logoSvg } from '../ui.js';
import { session, getProducts } from '../store.js';
import { api, getMode } from '../api.js';

const root = $('[data-admin]');
const logo = await logoSvg();
const asList = (x, key) => (Array.isArray(x) ? x : x?.[key] || x?.items || []);
const user = await session.load();

if (!user || user.role !== 'admin') {
  root.innerHTML = `<div class="wrap"><div class="empty" style="min-height:80vh"><a class="brand" href="index.html">${logo}<b class="wordmark">TridentWear</b></a>
    <h1 class="h2">Admin access only</h1><p class="muted">${user ? 'Your account does not have admin rights.' : 'Please sign in with an admin account.'}</p>
    <a class="btn" href="account.html?next=admin.html">Sign in</a>
    ${(await getMode()) === 'demo' ? '<p class="dev-hint">Preview mode admin: <b>admin@tridentwear.in</b> / <b>Admin@123</b></p>' : ''}</div></div>`;
  throw new Error('not admin');
}

const SECTIONS = [
  ['dashboard', 'Dashboard', icon.grid], ['products', 'Products', icon.bag], ['orders', 'Orders', icon.box],
  ['customers', 'Customers', icon.user], ['coupons', 'Coupons', icon.spark], ['reviews', 'Reviews', icon.heart],
];
root.innerHTML = `<div class="adm">
  <aside class="adm-side"><a class="brand" href="index.html">${logo}<b>ADMIN</b></a>
    ${SECTIONS.map(([k, l, i]) => `<button data-go="${k}">${i}${l}</button>`).join('')}
    <div class="spacer"></div><a href="index.html">${icon.home}View store</a><button data-logout>${icon.logout}Sign out</button></aside>
  <main class="adm-main" data-main></main></div>`;
$('[data-logout]').addEventListener('click', async () => { await session.logout(); location.href = 'account.html'; });
let main = $('[data-main]');
const go = (k) => {
  // fresh node per section so delegated listeners never stack
  const fresh = main.cloneNode(false); main.replaceWith(fresh); main = fresh;
  $$('[data-go]').forEach((b) => b.classList.toggle('is-on', b.dataset.go === k));
  history.replaceState(null, '', `#${k}`);
  main.innerHTML = '<div class="skeleton" style="height:320px"></div>';
  ({ dashboard, products, orders, customers, coupons, reviews })[k]().catch((e) => { main.innerHTML = `<p class="form-error">${esc(e.message)}</p>`; });
};
$$('[data-go]').forEach((b) => b.addEventListener('click', () => go(b.dataset.go)));
const top = (title, actions = '') => `<div class="adm-top"><div><span class="eyebrow">TridentWear admin</span><h1 class="h2" style="margin-top:6px">${title}</h1></div><div style="display:flex;gap:8px">${actions}</div></div>`;
const statusPill = (s) => `<span class="status status--${esc(String(s || '').toLowerCase())}">${esc(String(s || '—').replace('_', ' '))}</span>`;

// ------------------------------------------------------------------ dashboard
async function dashboard() {
  const a = await api.admin.analytics();
  const days = a.revenue_by_day || [];
  const max = Math.max(1, ...days.map((d) => d.revenue));
  const W = 700, H = 200, bw = W / Math.max(days.length, 1);
  const chart = `<svg class="chart" viewBox="0 0 ${W} ${H + 24}" preserveAspectRatio="none" role="img" aria-label="Revenue, last 14 days">
    ${days.map((d, i) => { const h = (d.revenue / max) * H; return `<rect x="${i * bw + 6}" y="${H - h}" width="${bw - 12}" height="${Math.max(h, 1)}" rx="4"><title>${d.date}: ${inr(d.revenue)} · ${d.orders} orders</title></rect><text x="${i * bw + bw / 2}" y="${H + 16}" text-anchor="middle">${d.date.slice(8)}</text>`; }).join('')}</svg>`;
  const topMax = Math.max(1, ...(a.top_products || []).map((t) => t.sold));
  main.innerHTML = `${top('Dashboard', '<button class="btn btn--sm" data-refresh>Refresh</button>')}
    <div class="kpis">
      <div class="kpi"><span>Revenue</span><b>${inr(a.total_revenue)}</b><small>${a.paid_orders ?? '—'} paid / COD orders</small></div>
      <div class="kpi"><span>Orders</span><b>${a.total_orders}</b><small>all statuses</small></div>
      <div class="kpi"><span>Avg order</span><b>${inr(a.average_order_value)}</b><small>${a.customers} customers</small></div>
      <div class="kpi"><span>Inventory</span><b>${a.total_stock_units}</b><small>${inr(a.inventory_value)} at retail</small></div>
    </div>
    <div class="adm-grid">
      <div class="card-box"><h3>Revenue · last 14 days</h3>${days.length ? chart : '<p class="muted">No sales yet.</p>'}</div>
      <div class="card-box"><h3>Orders by status</h3><div class="bar-list">${Object.entries(a.status_breakdown || {}).map(([k, v]) => `<div><span>${statusPill(k)}</span><b>${v}</b></div>`).join('') || '<p class="muted">No orders yet.</p>'}</div></div>
      <div class="card-box"><h3>Top sellers</h3><div class="bar-list">${(a.top_products || []).map((t) => `<div><span>${esc(t.name)}</span><b>${t.sold}</b><i><em style="width:${(t.sold / topMax) * 100}%"></em></i></div>`).join('') || '<p class="muted">No sales yet.</p>'}</div></div>
      <div class="card-box"><h3>Low stock · ${a.low_stock_count}</h3><div class="bar-list">${(a.low_stock_list || []).slice(0, 8).map((p) => `<div><span>${esc(p.name)}</span><b class="${p.stock ? 'stock-low' : 'stock-out'}">${p.stock || 'Out'}</b></div>`).join('') || '<p class="muted">All good.</p>'}</div></div>
    </div>`;
  $('[data-refresh]').addEventListener('click', () => go('dashboard'));
}

// ------------------------------------------------------------------ products
async function products() {
  const list = await getProducts(true);
  main.innerHTML = `${top('Products', '<button class="btn btn--sm" data-new>+ Add product</button>')}
    <div class="filters-row"><input class="input" placeholder="Search products" data-q><select class="select" data-cat><option value="">All categories</option><option value="tshirt">T-Shirts</option><option value="shirt">Shirts</option></select></div>
    <div class="table-wrap"><table class="t"><thead><tr><th></th><th>Product</th><th>Category</th><th>Price</th><th>Stock</th><th>Tag</th><th></th></tr></thead><tbody data-rows></tbody></table></div>`;
  const rows = () => {
    const q = $('[data-q]').value.toLowerCase(); const c = $('[data-cat]').value;
    $('[data-rows]').innerHTML = list.filter((p) => (!c || p.category === c) && `${p.name} ${p.base_color}`.toLowerCase().includes(q)).map((p) => `<tr>
      <td><img class="thumb" src="${img(p.image)}" alt=""></td>
      <td><b>${esc(p.name)}</b><div class="muted" style="font-size:12px">${esc(p.base_color || '')} · #${p.id}${p.featured ? ' · ★ featured' : ''}</div></td>
      <td>${p.category === 'shirt' ? 'Shirt' : 'T-Shirt'}</td>
      <td>${inr(p.price)}${p.mrp ? `<div class="muted" style="font-size:12px;text-decoration:line-through">${inr(p.mrp)}</div>` : ''}</td>
      <td class="${p.stock <= 0 ? 'stock-out' : p.stock <= 10 ? 'stock-low' : ''}">${p.stock}</td>
      <td>${esc(p.tag || '')}</td>
      <td><div class="row-actions"><button data-edit="${p.id}">Edit</button><button class="danger" data-del="${p.id}">Delete</button></div></td></tr>`).join('');
  };
  rows();
  $('[data-q]').addEventListener('input', rows); $('[data-cat]').addEventListener('change', rows);
  $('[data-new]').addEventListener('click', () => productForm());
  main.addEventListener('click', async (e) => {
    const ed = e.target.closest('[data-edit]'); const del = e.target.closest('[data-del]');
    if (ed) productForm(list.find((p) => p.id === Number(ed.dataset.edit)));
    if (del) {
      const p = list.find((x) => x.id === Number(del.dataset.del));
      if (!confirm(`Delete "${p.name} — ${p.base_color}"? This cannot be undone.`)) return;
      try { await api.admin.deleteProduct(p.id); toast('Product deleted'); go('products'); } catch (ex) { toast(ex.message, { type: 'error' }); }
    }
  });
}

function productForm(p = null) {
  const v = (k, d = '') => esc(p?.[k] ?? d);
  const m = modal(`<h3 class="h3">${p ? 'Edit product' : 'Add product'}</h3>
    <form class="form-grid" style="margin-top:16px" data-pf>
      <label class="field full"><span>Name</span><input class="input" name="name" required value="${v('name')}"></label>
      <label class="field"><span>Category</span><select class="select" name="category">${[['tshirt', 'T-Shirt'], ['shirt', 'Shirt']].map(([k, l]) => `<option value="${k}" ${p?.category === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      <label class="field"><span>Tag</span><input class="input" name="tag" value="${v('tag')}" placeholder="New, Bestseller…"></label>
      <label class="field"><span>Price (₹)</span><input class="input" name="price" type="number" min="1" required value="${v('price')}"></label>
      <label class="field"><span>MRP (₹, optional)</span><input class="input" name="mrp" type="number" min="0" value="${v('mrp')}"></label>
      <label class="field"><span>Colour name</span><input class="input" name="base_color" value="${v('base_color')}" placeholder="Jet Black"></label>
      <label class="field"><span>Swatch colour</span><input class="input" name="color_hex" type="color" value="${v('color_hex', '#17181b')}" style="padding:4px"></label>
      <label class="field"><span>Stock</span><input class="input" name="stock" type="number" min="0" required value="${v('stock', 0)}"></label>
      <label class="field"><span>Sizes</span><input class="input" name="sizes" value="${esc((p?.sizes || ['S', 'M', 'L', 'XL', 'XXL']).join(', '))}"></label>
      <label class="field"><span>Fabric</span><input class="input" name="fabric" value="${v('fabric', '100% Cotton')}"></label>
      <label class="field"><span>GSM</span><input class="input" name="gsm" type="number" min="80" max="400" value="${v('gsm', 220)}"></label>
      <label class="field"><span>Fit</span><select class="select" name="fit_type">${['Oversized', 'Regular', 'Slim', 'Relaxed'].map((f) => `<option ${p?.fit_type === f ? 'selected' : ''}>${f}</option>`).join('')}</select></label>
      <label class="field"><span>Neck / collar</span><input class="input" name="neck_type" value="${v('neck_type', 'Round Neck')}"></label>
      <label class="field full"><span>Description</span><textarea class="textarea" name="description">${v('description')}</textarea></label>
      <label class="img-drop full"><img src="${img(p?.image)}" alt="" data-prev><div><b>Product image</b><div class="muted" style="font-size:12.5px">PNG/WEBP with transparent background works best for AI Fit Check. Max 8MB.</div></div><input type="file" name="image" accept="image/png,image/jpeg,image/webp" hidden></label>
      <label class="check full"><input type="checkbox" name="featured_cb" ${p?.featured ? 'checked' : ''}> Feature on home page</label>
      <p class="form-error full" data-err></p>
      <button class="btn full">${p ? 'Save changes' : 'Create product'}</button>
    </form>`, { wide: true });
  const form = $('[data-pf]', m.el);
  form.image.addEventListener('change', () => { const f = form.image.files[0]; if (f) $('[data-prev]', m.el).src = URL.createObjectURL(f); });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!form.checkValidity()) { $('[data-err]', m.el).textContent = 'Please fill the required fields.'; return; }
    const fd = new FormData(form);
    fd.set('featured', form.featured_cb.checked ? 'true' : 'false'); fd.delete('featured_cb');
    if (!form.image.files.length) fd.delete('image');
    const btn = $('button.btn', form); busy(btn, true);
    try {
      p ? await api.admin.updateProduct(p.id, fd) : await api.admin.createProduct(fd);
      m.close(); toast(p ? 'Product updated' : 'Product created'); go('products');
    } catch (ex) { busy(btn, false); $('[data-err]', m.el).textContent = ex.message; }
  });
}

// ------------------------------------------------------------------ orders
const ORDER_STATUSES = ['placed', 'confirmed', 'packed', 'shipped', 'delivered', 'cancelled'];
async function orders() {
  const list = asList(await api.admin.orders(), 'orders').sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  main.innerHTML = `${top('Orders', `<button class="btn btn--ghost btn--sm" data-csv>Export CSV</button>`)}
    <div class="filters-row"><input class="input" placeholder="Search order ID, name, phone" data-q>
      <select class="select" data-st><option value="">All statuses</option>${ORDER_STATUSES.map((s) => `<option>${s}</option>`).join('')}</select></div>
    <div class="table-wrap"><table class="t"><thead><tr><th>Order</th><th>Date</th><th>Customer</th><th>Items</th><th>Total</th><th>Payment</th><th>Status</th><th></th></tr></thead><tbody data-rows></tbody></table></div>`;
  const filtered = () => {
    const q = $('[data-q]').value.toLowerCase(); const s = $('[data-st]').value;
    return list.filter((o) => (!s || o.status === s) && `${o.order_id} ${o.customer?.name} ${o.customer?.phone} ${o.customer?.email}`.toLowerCase().includes(q));
  };
  const rows = () => {
    const l = filtered();
    $('[data-rows]').innerHTML = l.length ? l.map((o) => `<tr>
      <td><b>${esc(o.order_id)}</b>${o.test_mode ? ' <span class="tag tag--line" style="height:18px">test</span>' : ''}</td><td>${fmtDate(o.created_at)}</td>
      <td>${esc(o.customer?.name || '')}<div class="muted" style="font-size:12px">${esc(o.customer?.phone || '')}</div></td>
      <td>${(o.items || []).reduce((s, i) => s + (i.qty || 1), 0)}</td><td>${inr(o.total ?? o.subtotal)}</td>
      <td>${statusPill(o.payment_status)}</td><td>${statusPill(o.status)}</td>
      <td><div class="row-actions"><button data-manage="${esc(o.order_id)}">Manage</button></div></td></tr>`).join('')
      : '<tr><td colspan="8" class="muted" style="text-align:center;padding:30px">No orders yet.</td></tr>';
  };
  rows();
  $('[data-q]').addEventListener('input', rows); $('[data-st]').addEventListener('change', rows);
  $('[data-csv]').addEventListener('click', () => {
    const head = ['order_id', 'created_at', 'name', 'phone', 'email', 'city', 'pincode', 'items', 'total', 'payment_status', 'status', 'tracking_id'];
    const lines = filtered().map((o) => [o.order_id, o.created_at, o.customer?.name, o.customer?.phone, o.customer?.email, o.shipping?.city, o.shipping?.pincode,
      (o.items || []).map((i) => `${i.name} ${i.size} x${i.qty}`).join(' | '), o.total ?? o.subtotal, o.payment_status, o.status, o.tracking_id || '']
      .map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([[head.join(','), ...lines].join('\n')], { type: 'text/csv' }));
    a.download = `tridentwear-orders-${new Date().toISOString().slice(0, 10)}.csv`; a.click();
  });
  main.addEventListener('click', (e) => { const b = e.target.closest('[data-manage]'); if (b) orderModal(list.find((o) => o.order_id === b.dataset.manage)); });
}

function orderModal(o) {
  const m = modal(`<h3 class="h3">${esc(o.order_id)}</h3><p class="muted" style="margin:4px 0 16px">${fmtDate(o.created_at)} · ${statusPill(o.payment_status)} ${o.razorpay_payment_id ? `· ${esc(o.razorpay_payment_id)}` : ''}</p>
    <div class="adm-grid" style="grid-template-columns:1fr 1fr">
      <div class="card-box"><h3>Items</h3>${(o.items || []).map((i) => `<div class="mini-line" style="margin-bottom:8px"><div class="line__img"><img src="${img(i.image)}" alt=""><em>${i.qty}</em></div><div>${esc(i.name)}<div class="muted" style="font-size:12px">Size ${esc(i.size)}</div></div><b>${inr(i.price * i.qty)}</b></div>`).join('')}
        <div class="totals" style="margin-top:10px"><div><span>Subtotal</span><span>${inr(o.subtotal)}</span></div>${o.discount_amount ? `<div><span>Discount ${esc(o.coupon_code || '')}</span><span>−${inr(o.discount_amount)}</span></div>` : ''}<div class="grand"><span>Total</span><span>${inr(o.total ?? o.subtotal)}</span></div></div></div>
      <div class="card-box"><h3>Ship to</h3><p style="margin:0;font-size:14px"><b>${esc(o.customer?.name)}</b><br>${esc(o.shipping?.address)}<br>${esc(o.shipping?.city)} ${esc(o.shipping?.state || '')} ${esc(o.shipping?.pincode || '')}<br>${esc(o.customer?.phone)}<br>${esc(o.customer?.email)}</p></div>
    </div>
    <form class="form-grid" style="margin-top:16px" data-of>
      <label class="field"><span>Order status</span><select class="select" name="status">${ORDER_STATUSES.map((s) => `<option ${o.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select></label>
      <label class="field"><span>Payment status</span><select class="select" name="payment_status">${['pending', 'paid', 'cod_pending', 'failed', 'refunded'].map((s) => `<option ${o.payment_status === s ? 'selected' : ''}>${s}</option>`).join('')}</select></label>
      <label class="field"><span>Courier</span><input class="input" name="courier" value="${esc(o.courier || '')}" placeholder="Delhivery, Blue Dart…"></label>
      <label class="field"><span>Tracking ID</span><input class="input" name="tracking_id" value="${esc(o.tracking_id || '')}"></label>
      <label class="field full"><span>Estimated delivery</span><input class="input" name="estimated_delivery" value="${esc(o.estimated_delivery || '')}" placeholder="e.g. 18 Nov 2026"></label>
      <p class="form-error full" data-err></p><button class="btn full">Update order</button></form>`, { wide: true });
  $('[data-of]', m.el).addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    Object.keys(f).forEach((k) => f[k] === '' && delete f[k]);
    if (f.status === 'cancelled' && !confirm('Cancel this order? Stock is restored and the customer will see it as cancelled.')) return;
    const btn = $('button.btn', e.target); busy(btn, true);
    try { await api.admin.updateOrder(o.order_id, f); m.close(); toast('Order updated'); go('orders'); }
    catch (ex) { busy(btn, false); $('[data-err]', m.el).textContent = ex.message; }
  });
}

// ------------------------------------------------------------------ customers
async function customers() {
  const list = asList(await api.admin.users(), 'users');
  main.innerHTML = `${top('Customers')}<div class="table-wrap"><table class="t"><thead><tr><th>Name</th><th>Email / phone</th><th>Role</th><th>Joined</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.map((u) => `<tr><td><b>${esc(u.name || '—')}</b></td><td>${esc(u.email || '')}<div class="muted" style="font-size:12px">${esc(u.phone || '')}</div></td>
      <td>${u.role === 'admin' ? '<span class="tag tag--violet">admin</span>' : 'customer'}</td><td>${fmtDate(u.created_at)}</td>
      <td>${u.is_active === false ? statusPill('cancelled').replace('cancelled', 'disabled') : statusPill('paid').replace('paid', 'active')}</td>
      <td><div class="row-actions">${u.id === user.id ? '<span class="muted" style="font-size:12px">you</span>' : `
        <button data-toggle="${u.id}" data-active="${u.is_active !== false}">${u.is_active === false ? 'Enable' : 'Disable'}</button>
        <button data-role="${u.id}" data-cur="${esc(u.role)}">${u.role === 'admin' ? 'Make customer' : 'Make admin'}</button>`}</div></td></tr>`).join('')}
    </tbody></table></div>`;
  main.addEventListener('click', async (e) => {
    const t = e.target.closest('[data-toggle]'); const r = e.target.closest('[data-role]');
    try {
      if (t) { await api.admin.setUserStatus(Number(t.dataset.toggle), t.dataset.active !== 'true'); toast('Customer updated'); go('customers'); }
      if (r) {
        const role = r.dataset.cur === 'admin' ? 'customer' : 'admin';
        if (role === 'admin' && !confirm('Give this user full admin access?')) return;
        await api.admin.setUserRole(Number(r.dataset.role), role); toast('Role updated'); go('customers');
      }
    } catch (ex) { toast(ex.message, { type: 'error' }); }
  });
}

// ------------------------------------------------------------------ coupons
async function coupons() {
  const list = asList(await api.admin.coupons(), 'coupons');
  main.innerHTML = `${top('Coupons', '<button class="btn btn--sm" data-new>+ New coupon</button>')}
    <div class="table-wrap"><table class="t"><thead><tr><th>Code</th><th>Discount</th><th>Used</th><th>Expires</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.map((c) => `<tr><td><b>${esc(c.code)}</b></td><td>${c.discount_pct}%</td><td>${c.usage_count || 0} / ${c.usage_limit}</td><td>${esc(c.expires_at || '')}</td>
      <td>${c.is_active ? statusPill('paid').replace('paid', 'active') : statusPill('cancelled').replace('cancelled', 'paused')}</td>
      <td><div class="row-actions"><button data-flip="${esc(c.code)}" data-on="${c.is_active}">${c.is_active ? 'Pause' : 'Activate'}</button><button class="danger" data-del="${esc(c.code)}">Delete</button></div></td></tr>`).join('')}
    </tbody></table></div>`;
  $('[data-new]').addEventListener('click', () => {
    const m = modal(`<h3 class="h3">New coupon</h3><form class="form-grid" style="margin-top:14px" data-cf>
      <label class="field"><span>Code</span><input class="input" name="code" required pattern="[A-Za-z0-9]{3,20}" style="text-transform:uppercase"></label>
      <label class="field"><span>Discount %</span><input class="input" name="discount_pct" type="number" min="1" max="90" required value="10"></label>
      <label class="field"><span>Expires on</span><input class="input" name="expires_at" type="date" required value="${new Date(Date.now() + 90 * 864e5).toISOString().slice(0, 10)}"></label>
      <label class="field"><span>Usage limit</span><input class="input" name="usage_limit" type="number" min="1" value="500"></label>
      <p class="form-error full" data-err></p><button class="btn full">Create coupon</button></form>`);
    $('[data-cf]', m.el).addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      try { await api.admin.createCoupon({ code: f.code.toUpperCase(), discount_pct: Number(f.discount_pct), expires_at: f.expires_at, usage_limit: Number(f.usage_limit), is_active: true }); m.close(); toast('Coupon created'); go('coupons'); }
      catch (ex) { $('[data-err]', m.el).textContent = ex.message; }
    });
  });
  main.addEventListener('click', async (e) => {
    const f = e.target.closest('[data-flip]'); const d = e.target.closest('[data-del]');
    try {
      if (f) { await api.admin.updateCoupon(f.dataset.flip, { is_active: f.dataset.on !== 'true' }); go('coupons'); }
      if (d && confirm(`Delete coupon ${d.dataset.del}?`)) { await api.admin.deleteCoupon(d.dataset.del); toast('Coupon deleted'); go('coupons'); }
    } catch (ex) { toast(ex.message, { type: 'error' }); }
  });
}

// ------------------------------------------------------------------ reviews
async function reviews() {
  const list = asList(await api.admin.reviews(), 'reviews');
  const prods = new Map((await getProducts()).map((p) => [p.id, p]));
  main.innerHTML = `${top('Reviews')}<div class="table-wrap"><table class="t"><thead><tr><th>Product</th><th>Rating</th><th>Review</th><th>By</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.length ? list.map((r) => `<tr><td>${esc(prods.get(r.product_id)?.name || '#' + r.product_id)}</td><td class="stars">${'★'.repeat(r.rating)}</td>
      <td style="max-width:360px">${esc(r.review || r.comment || '')}</td><td>${esc(r.user_name || r.name || '')}</td><td>${statusPill(r.status === 'approved' ? 'paid' : r.status === 'rejected' ? 'cancelled' : 'pending').replace(/>(paid|cancelled|pending)</, `>${esc(r.status || 'pending')}<`)}</td>
      <td><div class="row-actions"><button data-mod="${r.id}" data-s="approved">Approve</button><button data-mod="${r.id}" data-s="rejected">Reject</button><button class="danger" data-rdel="${r.id}">Delete</button></div></td></tr>`).join('')
      : '<tr><td colspan="6" class="muted" style="text-align:center;padding:30px">No reviews yet.</td></tr>'}</tbody></table></div>`;
  main.addEventListener('click', async (e) => {
    const m = e.target.closest('[data-mod]'); const d = e.target.closest('[data-rdel]');
    try {
      if (m) { await api.admin.moderateReview(Number(m.dataset.mod), m.dataset.s); toast(`Review ${m.dataset.s}`); go('reviews'); }
      if (d && confirm('Delete this review?')) { await api.admin.deleteReview(Number(d.dataset.rdel)); go('reviews'); }
    } catch (ex) { toast(ex.message, { type: 'error' }); }
  });
}

go(SECTIONS.some(([k]) => `#${k}` === location.hash) ? location.hash.slice(1) : 'dashboard');
