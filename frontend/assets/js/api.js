// API client: one interface, two adapters.
//   - "live": the FastAPI backend (/api/v1/*), bearer-token auth
//   - "demo": browser-only fallback (see demo.js) for static hosting like GitHub Pages
import { CONFIG } from './config.js';
import { demo } from './demo.js';

const TOKEN_KEY = 'tw_token';
const MODE_KEY = 'tw_mode';

export const auth = {
  get token() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; } },
  set token(v) { try { v ? localStorage.setItem(TOKEN_KEY, v) : localStorage.removeItem(TOKEN_KEY); } catch {} },
};

export class ApiError extends Error {
  constructor(message, status = 0, details = null) { super(message); this.status = status; this.details = details; }
}

let modePromise = null;
export function getMode() {
  if (modePromise) return modePromise;
  modePromise = (async () => {
    if (CONFIG.forceDemo) return 'demo';
    const cached = sessionStorage.getItem(MODE_KEY);
    if (cached) return cached;
    const onStaticHost = /github\.io$/.test(location.hostname) || location.protocol === 'file:';
    if (onStaticHost && !CONFIG.apiBase) return remember('demo');
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), CONFIG.healthTimeoutMs);
      const res = await fetch(`${CONFIG.apiBase}/api/v1/health`, { signal: ctrl.signal });
      clearTimeout(t);
      return remember(res.ok ? 'live' : 'demo');
    } catch {
      return remember('demo');
    }
  })();
  return modePromise;
}
function remember(m) { try { sessionStorage.setItem(MODE_KEY, m); } catch {} return m; }

async function request(path, { method = 'GET', body, form, idempotent = false } = {}) {
  const headers = {};
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (idempotent) headers['Idempotency-Key'] = crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random());
  let res;
  try {
    res = await fetch(`${CONFIG.apiBase}${path}`, {
      method, headers, credentials: 'include',
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch {
    throw new ApiError('Network error — please check your connection.', 0);
  }
  let json = null;
  try { json = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok || json?.success === false) {
    const msg = json?.error?.message || json?.detail || json?.data?.message || `Request failed (${res.status})`;
    if (res.status === 401 && auth.token) auth.token = '';
    throw new ApiError(msg, res.status, json?.error?.details);
  }
  // backend envelope: { success, data, error }; data may itself carry { success, ... }
  return json && 'data' in json ? json.data : json;
}

const live = {
  products: async () => (await request('/api/v1/products')).products,
  product: async (id) => (await request(`/api/v1/products/${id}`)).product,

  register: (p) => request('/api/v1/auth/register', { method: 'POST', body: p }),
  verifyEmail: (email, otp) => request('/api/auth/otp/verify-email', { method: 'POST', body: { email, otp } }),
  login: async (email, password) => {
    const d = await request('/api/v1/auth/login', { method: 'POST', body: { email, password } });
    auth.token = d.token; return d.user;
  },
  sendOtp: (phone) => request('/api/v1/auth/send-otp', { method: 'POST', body: { phone, country_code: '+91' } }),
  verifyOtp: async (phone, otp) => {
    const d = await request('/api/v1/auth/verify-otp', { method: 'POST', body: { phone, otp, country_code: '+91' } });
    auth.token = d.token; return d.user;
  },
  me: async () => {
    if (!auth.token) {
      // cookie session may still exist when backend serves the site
      try { const d = await request('/api/v1/auth/me'); return d.authenticated ? d.user : null; } catch { return null; }
    }
    try { const d = await request('/api/v1/auth/me'); return d.authenticated ? d.user : null; } catch { return null; }
  },
  logout: async () => { try { await request('/api/v1/auth/logout', { method: 'POST' }); } finally { auth.token = ''; } },
  requestReset: (email) => request('/api/v1/auth/password-reset/request', { method: 'POST', body: { email } }),
  confirmReset: (email, token, new_password) => request('/api/v1/auth/password-reset/confirm', { method: 'POST', body: { email, token, new_password } }),
  profile: () => request('/api/v1/account/profile'),
  updateProfile: (p) => request('/api/v1/account/profile', { method: 'PUT', body: p }),
  changePassword: (p) => request('/api/v1/account/password-change', { method: 'POST', body: p }),
  addresses: () => request('/api/v1/account/addresses').then((r) => r?.addresses || []),
  addAddress: (a) => request('/api/v1/account/addresses', { method: 'POST', body: a }),
  updateAddress: (id, a) => request(`/api/v1/account/addresses/${encodeURIComponent(id)}`, { method: 'PUT', body: a }),
  deleteAddress: (id) => request(`/api/v1/account/addresses/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  applyCoupon: (code, subtotal, items) => request('/api/v1/coupons/apply', { method: 'POST', body: { code, subtotal, items } }),
  createPayment: (order_data) => request('/api/v1/payments/create-order', { method: 'POST', body: { currency: 'INR', order_data }, idempotent: true }),
  verifyPayment: (p) => request('/api/v1/payments/verify', { method: 'POST', body: p, idempotent: true }),
  placeCod: (p) => request('/api/v1/payments/cod', { method: 'POST', body: p, idempotent: true }),
  orders: async () => (await request('/api/v1/orders')).orders || [],
  track: (id) => request(`/api/v1/orders/${encodeURIComponent(id)}/tracking`),
  cancelOrder: (id) => request(`/api/v1/orders/${encodeURIComponent(id)}/cancel`, { method: 'PUT' }),

  reviews: (pid) => request(`/api/v1/reviews/${pid}`),
  addReview: (p) => request('/api/v1/reviews', { method: 'POST', body: p }),
  wishlist: () => request('/api/v1/wishlist'),
  wishAdd: (product_id) => request('/api/v1/wishlist/add', { method: 'POST', body: { product_id } }),
  wishRemove: (product_id) => request('/api/v1/wishlist/remove', { method: 'POST', body: { product_id } }),
  contact: (p) => request('/api/v1/contact', { method: 'POST', body: p }),

  tryonStatus: () => request('/api/v1/tryon/status'),
  tryonGenerate: (form) => request('/api/v1/tryon/generate', { method: 'POST', form }),

  admin: {
    analytics: () => request('/api/v1/admin/analytics'),
    orders: () => request('/api/v1/admin/orders'),
    updateOrder: (id, p) => request(`/api/v1/admin/orders/${encodeURIComponent(id)}`, { method: 'PUT', body: p }),
    createProduct: (form) => request('/api/v1/admin/products', { method: 'POST', form }),
    updateProduct: (id, form) => request(`/api/v1/admin/products/${id}`, { method: 'PUT', form }),
    deleteProduct: (id) => request(`/api/v1/admin/products/${id}`, { method: 'DELETE' }),
    users: () => request('/api/v1/admin/users'),
    setUserStatus: (id, is_active) => request(`/api/v1/admin/users/${id}/status`, { method: 'PUT', body: { is_active } }),
    setUserRole: (id, role) => request(`/api/v1/admin/users/${id}/role`, { method: 'PUT', body: { role } }),
    coupons: () => request('/api/v1/admin/coupons'),
    createCoupon: (p) => request('/api/v1/admin/coupons', { method: 'POST', body: p }),
    updateCoupon: (code, p) => request(`/api/v1/admin/coupons/${encodeURIComponent(code)}`, { method: 'PUT', body: p }),
    deleteCoupon: (code) => request(`/api/v1/admin/coupons/${encodeURIComponent(code)}`, { method: 'DELETE' }),
    reviews: () => request('/api/v1/admin/reviews'),
    moderateReview: (id, status) => request(`/api/v1/admin/reviews/${id}`, { method: 'PUT', body: { status } }),
    deleteReview: (id) => request(`/api/v1/admin/reviews/${id}`, { method: 'DELETE' }),
  },
};

// Proxy picks the adapter lazily per call, so pages can just `await api.x()`.
function bind(liveObj, demoObj) {
  const out = {};
  for (const key of Object.keys(liveObj)) {
    if (typeof liveObj[key] === 'function') {
      out[key] = async (...args) => ((await getMode()) === 'live' ? liveObj[key] : demoObj[key])(...args);
    } else {
      out[key] = bind(liveObj[key], demoObj[key]);
    }
  }
  return out;
}
export const api = bind(live, demo);
