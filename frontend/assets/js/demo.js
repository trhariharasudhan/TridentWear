// DEMO adapter — used when no backend is reachable (e.g. GitHub Pages preview).
// Everything lives in this browser's localStorage. Payments are SIMULATED.
// Mirrors the live API's shapes so pages don't care which adapter is active.
import { CONFIG } from './config.js';

const KEY = 'tw_demo_db_v1';
const SESSION = 'tw_demo_session';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const now = () => new Date().toISOString();
const err = (message, status = 400) => Object.assign(new Error(message), { status });

let catalog = null;
async function seedProducts() {
  if (catalog) return catalog;
  const res = await fetch(new URL('../data/products.json', import.meta.url));
  catalog = await res.json();
  return catalog;
}

function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch { return null; }
}
function save(db) { localStorage.setItem(KEY, JSON.stringify(db)); }
async function db() {
  let d = load();
  if (!d) {
    d = {
      products: await seedProducts(),
      users: [{ id: 1, name: 'Trident Admin', email: CONFIG.demoAdmin.email, pw: await hash(CONFIG.demoAdmin.password), role: 'admin', is_active: true, verified: true, created_at: now() }],
      orders: [], reviews: [], wishlist: {}, contacts: [],
      coupons: [
        { code: 'TRIDENTFIRST', discount_pct: 20, expires_at: '2027-12-31', usage_limit: 1000, usage_count: 0, is_active: true },
        { code: 'TRIDENT10', discount_pct: 10, expires_at: '2027-12-31', usage_limit: 5000, usage_count: 0, is_active: true },
      ],
      pendingOtp: {},
    };
    save(d);
  }
  return d;
}
async function hash(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode('tw-demo:' + s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
const pub = (u) => u && ({ id: u.id, name: u.name, email: u.email, phone: u.phone || '', gender: u.gender || '', role: u.role, addresses: u.addresses || [] });
async function current() {
  const id = Number(localStorage.getItem(SESSION) || 0);
  if (!id) return null;
  return (await db()).users.find((u) => u.id === id) || null;
}
async function requireUser() { const u = await current(); if (!u) throw err('Please log in.', 401); return u; }
async function requireAdmin() { const u = await current(); if (!u || u.role !== 'admin') throw err('Access forbidden: Admins only.', 403); return u; }
const otp = () => String(Math.floor(100000 + Math.random() * 900000));
const orderId = () => 'TRD-' + Math.random().toString(16).slice(2, 10).toUpperCase();

function price(d, items, coupon) {
  const map = new Map(d.products.map((p) => [p.id, p]));
  const lines = items.map((i) => {
    const p = map.get(Number(i.id));
    if (!p) throw err(`Product with ID ${i.id} not found.`);
    const qty = Math.max(1, Math.min(50, Number(i.qty || 1)));
    if ((p.stock ?? 0) < qty) throw err(`Insufficient stock for ${p.name}.`);
    return { id: p.id, name: p.name, price: p.price, image: p.image, qty, size: String(i.size || '').toUpperCase(), base_color: p.base_color };
  });
  const subtotal = lines.reduce((s, l) => s + l.price * l.qty, 0);
  let discount = 0;
  if (coupon) {
    const c = d.coupons.find((x) => x.code === coupon.toUpperCase() && x.is_active);
    if (!c) throw err('Invalid coupon code.');
    discount = Math.round(subtotal * c.discount_pct) / 100;
  }
  return { lines, subtotal, discount, total: Math.max(0, subtotal - discount) };
}
function makeOrder(d, data, extra) {
  const { lines, subtotal, discount, total } = price(d, data.items, data.coupon_code);
  const user = d.users.find((u) => u.id === Number(localStorage.getItem(SESSION) || 0));
  const o = {
    id: d.orders.length + 1, order_id: orderId(), created_at: now(), updated_at: now(),
    items: lines, subtotal, discount_amount: discount, total, coupon_code: data.coupon_code || null,
    customer: { ...data.customer, user_id: user?.id }, shipping: data.shipping, status: 'placed', ...extra,
  };
  for (const l of lines) { const p = d.products.find((x) => x.id === l.id); p.stock = Math.max(0, (p.stock || 0) - l.qty); }
  if (data.coupon_code) { const c = d.coupons.find((x) => x.code === data.coupon_code.toUpperCase()); if (c) c.usage_count++; }
  d.orders.unshift(o);
  return o;
}

export const demo = {
  products: async () => (await db()).products,
  product: async (id) => { const p = (await db()).products.find((x) => x.id === Number(id)); if (!p) throw err('Product not found.', 404); return p; },

  register: async ({ name, email, password }) => {
    const d = await db(); email = String(email).trim().toLowerCase();
    if (d.users.some((u) => u.email === email)) throw err('An account with this email already exists.');
    if (String(password).length < 8) throw err('Password must be at least 8 characters.');
    const code = otp();
    d.users.push({ id: d.users.length + 1, name, email, pw: await hash(password), role: 'customer', is_active: true, verified: false, otp: code, created_at: now() });
    save(d); await sleep(300);
    return { success: true, email, dev_otp: code, message: `Account created. (Demo OTP: ${code})` };
  },
  verifyEmail: async (email, code) => {
    const d = await db(); const u = d.users.find((x) => x.email === email.toLowerCase());
    if (!u) throw err('User not found.', 404);
    if (u.otp !== String(code).trim()) throw err('Invalid OTP.');
    u.verified = true; delete u.otp; save(d);
    return { success: true, user: pub(u) };
  },
  login: async (email, password) => {
    const d = await db(); const u = d.users.find((x) => x.email === String(email).trim().toLowerCase());
    await sleep(250);
    if (!u || u.pw !== (await hash(password))) throw err('Incorrect email or password.', 401);
    if (!u.is_active) throw err('This account is deactivated.', 403);
    if (!u.verified && u.role !== 'admin') throw err('Please verify your email OTP before logging in.', 403);
    localStorage.setItem(SESSION, String(u.id));
    return pub(u);
  },
  sendOtp: async (phone) => {
    const d = await db(); const code = otp(); d.pendingOtp[phone] = code; save(d);
    return { success: true, dev_otp: code, message: `OTP sent (Demo OTP: ${code})` };
  },
  verifyOtp: async (phone, code) => {
    const d = await db();
    if (d.pendingOtp[phone] !== String(code)) throw err('Invalid OTP.');
    let u = d.users.find((x) => x.phone === phone);
    if (!u) { u = { id: d.users.length + 1, name: 'Trident Member', email: `${phone}@phone.demo`, phone, role: 'customer', is_active: true, verified: true, created_at: now() }; d.users.push(u); }
    delete d.pendingOtp[phone]; save(d); localStorage.setItem(SESSION, String(u.id));
    return pub(u);
  },
  me: async () => pub(await current()),
  logout: async () => localStorage.removeItem(SESSION),
  requestReset: async () => ({ success: true, message: 'Demo mode: password reset emails are not sent.' }),
  confirmReset: async () => ({ success: true }),
  profile: async () => { const u = await requireUser(); const d = await db(); const raw = d.users.find((x) => x.id === u.id) || {}; return { user: pub(u), settings: { order_updates_email: true, order_updates_whatsapp: false, new_drops: true, marketing: false, ...(raw.settings || {}) }, birthday: raw.birthday || null }; },
  updateProfile: async (p) => {
    const me = await requireUser(); const d = await db(); const u = d.users.find((x) => x.id === me.id);
    Object.assign(u, Object.fromEntries(Object.entries(p).filter(([, v]) => v !== undefined))); save(d);
    return { success: true, user: pub(u) };
  },
  changePassword: async () => ({ success: true, message: 'Demo mode: password unchanged.' }),
  deleteAccount: async ({ confirm }) => { if (String(confirm).toUpperCase() !== 'DELETE') throw err('Type DELETE to confirm.'); const me = await requireUser(); const d = await db(); d.users = d.users.filter((x) => x.id !== me.id); save(d); localStorage.removeItem(SESSION); return { success: true, message: 'Your account has been deleted.' }; },
  addresses: async () => { const me = await requireUser(); const d = await db(); return (d.addresses || []).filter((a) => a.user_id === me.id).sort((a, b) => b.is_default - a.is_default); },
  addAddress: async (a) => {
    const me = await requireUser(); const d = await db(); d.addresses ||= [];
    if (!/^[1-9][0-9]{5}$/.test(String(a.pin || ''))) throw err('Enter a valid 6-digit PIN code.');
    const mine = d.addresses.filter((x) => x.user_id === me.id);
    const isDefault = !!a.is_default || !mine.length;
    if (isDefault) mine.forEach((x) => (x.is_default = false));
    const row = { address_id: 'ADR-' + Math.random().toString(36).slice(2, 12).toUpperCase(), user_id: me.id, label: a.label || 'Home', street: a.street, area: a.area || '', city: a.city, state: a.state, pin: a.pin, country: 'India', is_default: isDefault };
    d.addresses.push(row); save(d); return { address: row };
  },
  updateAddress: async (id, a) => {
    const me = await requireUser(); const d = await db(); const row = (d.addresses || []).find((x) => x.address_id === id && x.user_id === me.id);
    if (!row) throw err('Address not found.', 404);
    if (a.is_default) d.addresses.filter((x) => x.user_id === me.id).forEach((x) => (x.is_default = false));
    Object.assign(row, a); save(d); return { address: row };
  },
  deleteAddress: async (id) => {
    const me = await requireUser(); const d = await db(); const row = (d.addresses || []).find((x) => x.address_id === id && x.user_id === me.id);
    if (!row) throw err('Address not found.', 404);
    d.addresses = d.addresses.filter((x) => x !== row);
    if (row.is_default) { const next = d.addresses.find((x) => x.user_id === me.id); if (next) next.is_default = true; }
    save(d); return { success: true };
  },

  applyCoupon: async (code, subtotal) => {
    const d = await db(); const c = d.coupons.find((x) => x.code === String(code).trim().toUpperCase());
    if (!c || !c.is_active) throw err('Invalid coupon code.');
    const discount = Math.round(subtotal * c.discount_pct) / 100;
    return { success: true, code: c.code, discount_pct: c.discount_pct, discount_amount: discount, new_total: subtotal - discount };
  },
  createPayment: async (data) => {
    const d = await db(); const { total } = price(d, data.items, data.coupon_code);
    const o = { order_id: orderId(), razorpay_order_id: 'order_demo_' + Date.now(), amount: Math.round(total * 100), currency: 'INR', key_id: 'rzp_test_mockkey', demo: true };
    d.pendingPay = { ...o, data }; save(d);
    return { success: true, ...o };
  },
  verifyPayment: async ({ razorpay_order_id, razorpay_payment_id }) => {
    const d = await db();
    if (!d.pendingPay || d.pendingPay.razorpay_order_id !== razorpay_order_id) throw err('Payment session expired.');
    const o = makeOrder(d, d.pendingPay.data, { payment_method: 'razorpay', payment_status: 'paid', razorpay_order_id, razorpay_payment_id, order_id: d.pendingPay.order_id });
    delete d.pendingPay; save(d);
    return { success: true, order_id: o.order_id, message: 'Payment verified and order placed' };
  },
  placeCod: async (data) => {
    const d = await db(); const o = makeOrder(d, data, { payment_method: 'cod', payment_status: 'cod_pending' }); save(d); await sleep(400);
    return { success: true, order_id: o.order_id, message: 'COD order placed successfully' };
  },
  orders: async () => { const u = await requireUser(); return (await db()).orders.filter((o) => o.customer?.user_id === u.id); },
  track: async (id) => {
    const o = (await db()).orders.find((x) => x.order_id === id); if (!o) throw err('Order not found.', 404);
    return { status: o.status, courier: o.courier || 'Pending Allocation', tracking_id: o.tracking_id || null, estimated_delivery: o.estimated_delivery || 'Tracking will be updated soon', order: o };
  },
  cancelOrder: async (id) => {
    const d = await db(); const o = d.orders.find((x) => x.order_id === id); if (!o) throw err('Order not found.', 404);
    if (!['placed', 'processing', 'confirmed'].includes(o.status)) throw err('This order can no longer be cancelled.');
    o.status = 'cancelled'; save(d); return { success: true };
  },

  reviews: async (pid) => {
    const list = (await db()).reviews.filter((r) => r.product_id === Number(pid) && r.status === 'approved');
    const bars = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 }; list.forEach((r) => bars[r.rating]++);
    return { product_id: pid, count: list.length, average: list.length ? +(list.reduce((s, r) => s + r.rating, 0) / list.length).toFixed(1) : 0, bars, reviews: list };
  },
  addReview: async ({ product_id, rating, review }) => {
    const u = await requireUser(); const d = await db();
    d.reviews.push({ id: d.reviews.length + 1, product_id, rating, review, user_name: u.name, status: 'pending', created_at: now() }); save(d);
    return { success: true, message: 'Review submitted for moderation.' };
  },
  wishlist: async () => [], wishAdd: async () => ({ success: true }), wishRemove: async () => ({ success: true }),
  contact: async (p) => { const d = await db(); d.contacts.push({ ...p, created_at: now() }); save(d); return { success: true, message: 'Thanks! We will get back to you shortly.' }; },

  site: async () => { try { return JSON.parse(localStorage.getItem('tw_demo_site') || 'null') || {}; } catch { return {}; } },
  tryonStatus: async () => ({ ai_enabled: false, provider: null, live_ar: true }),
  tryonGenerate: async () => { throw err('AI render needs the backend with REPLICATE_API_TOKEN configured.', 503); },

  admin: {
    saveSite: async (p) => { await requireAdmin(); const cur = JSON.parse(localStorage.getItem('tw_demo_site') || '{}'); const next = { ...cur, ...p, contact: { ...(cur.contact || {}), ...(p.contact || {}) } }; localStorage.setItem('tw_demo_site', JSON.stringify(next)); return next; },
    analytics: async () => {
      await requireAdmin(); const d = await db();
      const sales = d.orders.filter((o) => o.status !== 'cancelled' && ['paid', 'cod_pending'].includes(o.payment_status));
      const revenue = sales.reduce((s, o) => s + o.total, 0);
      const sold = {}; sales.forEach((o) => o.items.forEach((i) => (sold[i.name] = (sold[i.name] || 0) + i.qty)));
      const days = [...Array(14)].map((_, i) => { const dt = new Date(Date.now() - (13 - i) * 864e5).toISOString().slice(0, 10); return { date: dt, revenue: 0, orders: 0 }; });
      sales.forEach((o) => { const r = days.find((x) => x.date === o.created_at.slice(0, 10)); if (r) { r.revenue += o.total; r.orders++; } });
      const status_breakdown = {}; d.orders.forEach((o) => (status_breakdown[o.status] = (status_breakdown[o.status] || 0) + 1));
      return {
        total_orders: d.orders.length, paid_orders: sales.length, total_revenue: revenue, customers: new Set(d.orders.map((o) => o.customer?.email)).size,
        average_order_value: sales.length ? Math.round(revenue / sales.length) : 0,
        top_products: Object.entries(sold).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([name, s]) => ({ name, sold: s })),
        total_products: d.products.length, total_stock_units: d.products.reduce((s, p) => s + (p.stock || 0), 0),
        low_stock_count: d.products.filter((p) => p.stock <= 10).length, out_of_stock_count: d.products.filter((p) => !p.stock).length,
        low_stock_list: d.products.filter((p) => p.stock <= 10).map((p) => ({ name: `${p.name} — ${p.base_color}`, category: p.category, stock: p.stock })),
        inventory_value: d.products.reduce((s, p) => s + p.price * (p.stock || 0), 0), revenue_by_day: days, status_breakdown,
      };
    },
    orders: async () => { await requireAdmin(); return (await db()).orders; },
    updateOrder: async (id, p) => { await requireAdmin(); const d = await db(); const o = d.orders.find((x) => x.order_id === id); Object.assign(o, p, { updated_at: now() }); save(d); return { success: true, order: o }; },
    createProduct: async (form) => {
      await requireAdmin(); const d = await db(); const f = Object.fromEntries(form.entries());
      const id = Math.max(0, ...d.products.map((p) => p.id)) + 1;
      let image = '/images/products/essential-oversized-tee-jet-black-front.webp';
      if (f.image && f.image.size) image = await fileToDataUrl(f.image);
      const p = { id, name: f.name, category: f.category, price: +f.price, mrp: +f.mrp || undefined, description: f.description, tag: f.tag, sizes: f.sizes.split(',').map((s) => s.trim()), stock: +f.stock, featured: f.featured === 'true', base_color: f.base_color, color_hex: f.color_hex, fabric: f.fabric, gsm: +f.gsm, fit_type: f.fit_type, neck_type: f.neck_type, image, gallery: [image] };
      d.products.push(p); save(d); return { success: true, product: p };
    },
    updateProduct: async (id, form) => {
      await requireAdmin(); const d = await db(); const p = d.products.find((x) => x.id === Number(id)); const f = Object.fromEntries(form.entries());
      Object.assign(p, { name: f.name, category: f.category, price: +f.price, mrp: +f.mrp || p.mrp, description: f.description, tag: f.tag, sizes: f.sizes.split(',').map((s) => s.trim()), stock: +f.stock, featured: f.featured === 'true', base_color: f.base_color || p.base_color, color_hex: f.color_hex || p.color_hex, fabric: f.fabric, gsm: +f.gsm, fit_type: f.fit_type, neck_type: f.neck_type });
      if (f.image && f.image.size) { p.image = await fileToDataUrl(f.image); p.gallery = [p.image]; }
      save(d); return { success: true, product: p };
    },
    deleteProduct: async (id) => { await requireAdmin(); const d = await db(); d.products = d.products.filter((x) => x.id !== Number(id)); save(d); return { success: true }; },
    users: async () => { await requireAdmin(); return (await db()).users.map((u) => ({ ...pub(u), is_active: u.is_active, created_at: u.created_at })); },
    setUserStatus: async (id, is_active) => { await requireAdmin(); const d = await db(); d.users.find((u) => u.id === id).is_active = is_active; save(d); return { success: true }; },
    setUserRole: async (id, role) => { await requireAdmin(); const d = await db(); d.users.find((u) => u.id === id).role = role; save(d); return { success: true }; },
    coupons: async () => { await requireAdmin(); return (await db()).coupons; },
    createCoupon: async (c) => { await requireAdmin(); const d = await db(); c.code = c.code.toUpperCase(); if (d.coupons.some((x) => x.code === c.code)) throw err('Coupon already exists.'); d.coupons.push({ usage_count: 0, ...c }); save(d); return { success: true }; },
    updateCoupon: async (code, p) => { await requireAdmin(); const d = await db(); Object.assign(d.coupons.find((x) => x.code === code), p); save(d); return { success: true }; },
    deleteCoupon: async (code) => { await requireAdmin(); const d = await db(); d.coupons = d.coupons.filter((x) => x.code !== code); save(d); return { success: true }; },
    reviews: async () => { await requireAdmin(); return (await db()).reviews; },
    moderateReview: async (id, status) => { await requireAdmin(); const d = await db(); d.reviews.find((r) => r.id === id).status = status; save(d); return { success: true }; },
    deleteReview: async (id) => { await requireAdmin(); const d = await db(); d.reviews = d.reviews.filter((r) => r.id !== id); save(d); return { success: true }; },
  },
};

function fileToDataUrl(file) {
  return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(file); });
}
