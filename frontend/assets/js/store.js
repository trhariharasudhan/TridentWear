// Client state: catalog cache, cart, wishlist, signed-in user. Emits 'tw:*' events.
import { api } from './api.js';

const CART_KEY = 'tw_cart_v2';
const WISH_KEY = 'tw_wish_v2';
const read = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };
const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));

// ---------- catalog
let productsPromise = null;
export function getProducts(force = false) {
  if (!productsPromise || force) productsPromise = api.products().catch((e) => { productsPromise = null; throw e; });
  return productsPromise;
}
export async function getProduct(id) {
  const list = await getProducts();
  return list.find((p) => p.id === Number(id)) || api.product(id);
}
export async function siblings(product) {
  if (!product.style_code) return [product];
  return (await getProducts()).filter((p) => p.style_code === product.style_code);
}

// ---------- cart: [{ id, size, qty }]
export const cart = {
  get items() { return read(CART_KEY, []); },
  set items(v) { write(CART_KEY, v); emit('tw:cart', v); },
  count() { return this.items.reduce((s, i) => s + i.qty, 0); },
  add(id, size, qty = 1) {
    const items = this.items;
    const hit = items.find((i) => i.id === id && i.size === size);
    if (hit) hit.qty = Math.min(10, hit.qty + qty); else items.push({ id, size, qty });
    this.items = items;
  },
  setQty(id, size, qty) {
    let items = this.items;
    if (qty <= 0) items = items.filter((i) => !(i.id === id && i.size === size));
    else items.forEach((i) => { if (i.id === id && i.size === size) i.qty = Math.min(10, qty); });
    this.items = items;
  },
  remove(id, size) { this.setQty(id, size, 0); },
  clear() { this.items = []; },
  async detailed() {
    const products = await getProducts();
    const map = new Map(products.map((p) => [p.id, p]));
    const lines = this.items.map((i) => ({ ...i, product: map.get(i.id) })).filter((l) => l.product);
    const subtotal = lines.reduce((s, l) => s + l.product.price * l.qty, 0);
    const mrpTotal = lines.reduce((s, l) => s + (l.product.mrp || l.product.price) * l.qty, 0);
    return { lines, subtotal, savings: mrpTotal - subtotal };
  },
  // payload shape the backend expects
  asOrderItems() { return this.items.map((i) => ({ id: i.id, qty: i.qty, size: i.size })); },
};

// ---------- wishlist: [productId] (local; synced to backend when signed in)
export const wishlist = {
  get ids() { return read(WISH_KEY, []); },
  has(id) { return this.ids.includes(id); },
  toggle(id) {
    const on = !this.has(id);
    write(WISH_KEY, on ? [...this.ids, id] : this.ids.filter((x) => x !== id));
    emit('tw:wish', this.ids);
    if (session.user) (on ? api.wishAdd(id) : api.wishRemove(id)).catch(() => {});
    return on;
  },
  async syncFromServer() {
    try {
      const remote = await api.wishlist();
      const ids = (Array.isArray(remote) ? remote : remote?.items || []).map((r) => Number(r.product_id ?? r.id)).filter(Boolean);
      const merged = [...new Set([...this.ids, ...ids])];
      write(WISH_KEY, merged); emit('tw:wish', merged);
      for (const id of this.ids) if (!ids.includes(id)) api.wishAdd(id).catch(() => {});
    } catch { /* offline or demo */ }
  },
};

// ---------- session
export const session = {
  user: null,
  ready: null,
  async load() {
    this.ready = this.ready || api.me().then((u) => { this.user = u; emit('tw:user', u); if (u) wishlist.syncFromServer(); return u; }).catch(() => null);
    return this.ready;
  },
  set(u) { this.user = u; this.ready = Promise.resolve(u); emit('tw:user', u); if (u) wishlist.syncFromServer(); },
  async logout() { await api.logout(); this.set(null); },
};
