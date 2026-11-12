// Shared UI: header/footer/drawers/tab bar, product cards, toasts, modals, helpers.
import { CONFIG } from './config.js';
import { getMode, api } from './api.js';
import { cart, wishlist, session, getProducts } from './store.js';

// ---------------------------------------------------------------- helpers
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const inr = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
export const params = () => new URLSearchParams(location.search);
// product image paths come from the API as "/images/..."; map to the static asset folder
export const img = (p) => {
  if (!p) return 'assets/images/products/essential-oversized-tee-jet-black-front.webp';
  if (p.startsWith('data:') || /^https?:/.test(p)) return p;
  if (p.startsWith('/images/')) return 'assets/images/' + p.slice(8);
  if (p.startsWith('/assets/')) return p.slice(1);
  return p;
};
export const gallery = (p) => (p.gallery?.length ? p.gallery : [p.image]).map(img);
// every product image ships a 480w variant next to the full 900w file
export const srcset = (src) => (/\/products\/[^/]+\.webp$/.test(src) ? `${src.replace(/\.webp$/, '-480.webp')} 480w, ${src} 900w` : '');
const SIZES = '(max-width: 640px) 48vw, (max-width: 1100px) 32vw, 300px';
export const fullName = (p) => (p.base_color ? `${p.name} — ${p.base_color}` : p.name);
export const discountPct = (p) => (p.mrp && p.mrp > p.price ? Math.round((1 - p.price / p.mrp) * 100) : 0);
export const fmtDate = (s) => (s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '');

// ---------------------------------------------------------------- icons
const I = (d, extra = '') => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" ${extra}>${d}</svg>`;
export const icon = {
  search: I('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
  heart: I('<path d="M12 20s-7-4.4-9.2-9A5 5 0 0 1 12 6a5 5 0 0 1 9.2 5C19 15.6 12 20 12 20Z"/>'),
  user: I('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
  bag: I('<path d="M5 8h14l-1 12H6L5 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>'),
  menu: I('<path d="M4 7h16M4 12h16M4 17h10"/>'),
  close: I('<path d="M6 6l12 12M18 6 6 18"/>'),
  home: I('<path d="M4 11 12 4l8 7v9H4v-9Z"/><path d="M10 20v-5h4v5"/>'),
  grid: I('<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>'),
  camera: I('<path d="M4 8h3l2-3h6l2 3h3v11H4V8Z"/><circle cx="12" cy="13" r="3.5"/>'),
  spark: I('<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>'),
  truck: I('<path d="M3 7h11v9H3zM14 10h4l3 3v3h-7"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/>'),
  swap: I('<path d="M4 8h13l-3-3M20 16H7l3 3"/>'),
  shield: I('<path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6l-7-3Z"/><path d="m9 12 2 2 4-4"/>'),
  cash: I('<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/>'),
  ruler: I('<path d="M4 16 16 4l4 4L8 20l-4-4Z"/><path d="M8 12l2 2M11 9l2 2M14 6l2 2"/>'),
  check: I('<path d="m5 12 5 5L20 7"/>', 'stroke-width="3"'),
  plus: I('<path d="M12 5v14M5 12h14"/>'),
  minus: I('<path d="M5 12h14"/>'),
  arrow: I('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  mail: I('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>'),
  phone: I('<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z"/>'),
  pin: I('<path d="M12 21s-7-6-7-11a7 7 0 0 1 14 0c0 5-7 11-7 11Z"/><circle cx="12" cy="10" r="2.5"/>'),
  box: I('<path d="M3 7l9-4 9 4v10l-9 4-9-4V7Z"/><path d="m3 7 9 4 9-4M12 11v10"/>'),
  logout: I('<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10"/>'),
  insta: I('<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r=".8" fill="currentColor"/>'),
  whatsapp: I('<path d="M4 20l1.3-4A8 8 0 1 1 8 18.7L4 20Z"/><path d="M9 9.5c.5 2 2.5 4 4.5 4.5l1-1.2 2 .8c-.3 1.4-1.4 2-2.6 1.8A7 7 0 0 1 8 9.8c-.2-1.2.4-2.3 1.8-2.6l.8 2-1 1Z"/>'),
  flip: I('<path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/>'),
  upload: I('<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>'),
  download: I('<path d="M12 4v12M7 11l5 5 5-5M4 20h16"/>'),
  share: I('<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4"/>'),
};
let LOGO = '';
export async function logoSvg() {
  if (LOGO) return LOGO;
  try {
    const t = await (await fetch(new URL('../brand/logo-mark.svg', import.meta.url))).text();
    LOGO = t.replace('<svg ', '<svg aria-hidden="true" ');
  } catch { LOGO = ''; }
  return LOGO;
}

// ---------------------------------------------------------------- toasts & modals
export function toast(message, { type = 'info', image, link, timeout = 3200 } = {}) {
  let host = $('.toasts');
  if (!host) { host = document.createElement('div'); host.className = 'toasts'; host.setAttribute('role', 'status'); document.body.append(host); }
  const t = document.createElement('div');
  t.className = `toast ${type === 'error' ? 'toast--error' : ''}`;
  t.innerHTML = `${image ? `<img src="${esc(image)}" alt="">` : ''}<span>${esc(message)}${link ? ` <a href="${esc(link.href)}">${esc(link.label)}</a>` : ''}</span>`;
  host.append(t);
  setTimeout(() => { t.classList.add('is-out'); setTimeout(() => t.remove(), 300); }, timeout);
}
export function modal(html, { wide = false, onClose } = {}) {
  const m = document.createElement('div');
  m.className = `modal ${wide ? 'modal--wide' : ''}`;
  m.innerHTML = `<div class="modal__box" role="dialog" aria-modal="true"><button class="icon-btn modal__close" aria-label="Close">${icon.close}</button>${html}</div>`;
  const close = () => { m.classList.remove('is-open'); setTimeout(() => m.remove(), 300); document.removeEventListener('keydown', onKey); onClose?.(); };
  const onKey = (e) => e.key === 'Escape' && close();
  m.addEventListener('click', (e) => { if (e.target === m || e.target.closest('.modal__close')) close(); });
  document.addEventListener('keydown', onKey);
  document.body.append(m);
  requestAnimationFrame(() => m.classList.add('is-open'));
  return { el: m, box: $('.modal__box', m), close };
}
export function busy(btn, on, label) {
  if (!btn) return;
  if (on) { btn.dataset.label = btn.innerHTML; btn.classList.add('is-loading'); btn.innerHTML = `<i class="spin"></i>${label ? esc(label) : ''}`; }
  else { btn.classList.remove('is-loading'); if (btn.dataset.label) btn.innerHTML = btn.dataset.label; }
}

// ---------------------------------------------------------------- product card
export function productCard(p, { lazy = true } = {}) {
  const [front, back] = gallery(p);
  const off = discountPct(p);
  const wish = wishlist.has(p.id);
  const tags = [p.tag && `<span class="tag ${/limited|drop/i.test(p.tag) ? 'tag--violet' : /new/i.test(p.tag) ? 'tag--amber' : ''}">${esc(p.tag)}</span>`].filter(Boolean).join('');
  return `<article class="card" data-id="${p.id}">
    <a class="card__media" href="product.html?id=${p.id}" aria-label="${esc(fullName(p))}">
      <img class="img-front" src="${front}" srcset="${srcset(front)}" sizes="${SIZES}" width="900" height="1080" alt="${esc(fullName(p))}" ${lazy ? 'loading="lazy"' : 'fetchpriority="high"'} decoding="async">
      ${back ? `<img class="img-back" src="${back}" srcset="${srcset(back)}" sizes="${SIZES}" width="900" height="1080" alt="" loading="lazy" decoding="async">` : ''}
      ${p.stock <= 0 ? '<span class="oos">Sold out</span>' : ''}
    </a>
    <div class="card__tags">${tags}</div>
    <button class="icon-btn card__wish ${wish ? 'is-on' : ''}" data-wish="${p.id}" aria-pressed="${wish}" aria-label="Save to wishlist">${icon.heart}</button>
    ${p.stock > 0 ? `<div class="card__quick">${(p.sizes || []).slice(0, 5).map((s) => `<button class="sz" data-quick="${p.id}" data-size="${esc(s)}" aria-label="Add size ${esc(s)}">${esc(s)}</button>`).join('')}</div>` : ''}
    <div class="card__info">
      <a class="card__name" href="product.html?id=${p.id}">${esc(p.name)}</a>
      <div class="card__meta"><span>${esc(p.base_color || '')}</span>${p.color_hex ? `<span class="swatches"><i class="swatch" style="background:${esc(p.color_hex)}"></i></span>` : ''}</div>
      <div><span class="price">${inr(p.price)}</span>${off ? `<span class="mrp">${inr(p.mrp)}</span><span class="off">${off}% off</span>` : ''}</div>
    </div>
  </article>`;
}
// delegated handlers for wishlist hearts + quick-add size buttons
document.addEventListener('click', async (e) => {
  const w = e.target.closest('[data-wish]');
  if (w) {
    e.preventDefault();
    const on = wishlist.toggle(Number(w.dataset.wish));
    $$(`[data-wish="${w.dataset.wish}"]`).forEach((b) => { b.classList.toggle('is-on', on); b.setAttribute('aria-pressed', on); });
    toast(on ? 'Saved to wishlist' : 'Removed from wishlist', on ? { link: { href: 'wishlist.html', label: 'View' } } : {});
    return;
  }
  const q = e.target.closest('[data-quick]');
  if (q) {
    e.preventDefault();
    const id = Number(q.dataset.quick);
    cart.add(id, q.dataset.size, 1);
    const p = (await getProducts()).find((x) => x.id === id);
    toast(`Added ${p?.name || 'item'} (${q.dataset.size})`, { image: p && img(p.image), link: { href: 'cart.html', label: 'View bag' } });
  }
});

// ---------------------------------------------------------------- reveal on scroll
export function reveal(root = document) {
  const els = $$('.reveal:not(.is-in)', root);
  if (!('IntersectionObserver' in window)) return els.forEach((e) => e.classList.add('is-in'));
  const io = new IntersectionObserver((entries) => entries.forEach((en) => { if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); } }), { rootMargin: '0px 0px -8% 0px' });
  els.forEach((e) => io.observe(e));
}

// ---------------------------------------------------------------- chrome (header/footer/drawers)
const NAV = [
  ['shop.html', 'Shop all', 'shop'],
  ['shop.html?cat=tshirt', 'T-Shirts', 'tshirt'],
  ['shop.html?cat=shirt', 'Shirts', 'shirt'],
  ['tryon.html', 'Fit Check<span class="ai">AI</span>', 'tryon'],
  ['about.html', 'Story', 'about'],
];

let ANNOUNCEMENTS = [
  'Free shipping on every order across India',
  'Use code <b>TRIDENTFIRST</b> for 20% off your first order',
  `${CONFIG.returnDays}-day exchanges, no questions asked`,
  'See it on you first with <b>AI Fit Check</b>',
];

// Admin-editable storefront settings (Admin > Storefront). Cached for a minute per tab.
let SITE = null;
export async function siteSettings() {
  if (SITE) return SITE;
  try {
    const cached = JSON.parse(sessionStorage.getItem('tw_site') || 'null');
    if (cached && Date.now() - cached.at < 60_000) return (SITE = cached.site);
  } catch { /* ignore */ }
  try { SITE = (await api.site()) || {}; } catch { SITE = {}; }
  try { sessionStorage.setItem('tw_site', JSON.stringify({ at: Date.now(), site: SITE })); } catch { /* ignore */ }
  return SITE;
}
// escape, then bold codes written in capitals (e.g. TRIDENTFIRST) so they stand out
const announce = (t) => esc(t).replace(/\b([A-Z0-9]{6,})\b/g, '<b>$1</b>');

export async function mountChrome({ page = '', overlayHeader = false } = {}) {
  const [logo, site] = await Promise.all([logoSvg(), siteSettings()]);
  if (site.contact) Object.assign(CONFIG.brand, Object.fromEntries(Object.entries(site.contact).filter(([, v]) => v)));
  if (site.announcements?.length) ANNOUNCEMENTS = site.announcements.map(announce);
  document.documentElement.style.setProperty('--logo-mask', `url("${new URL('../brand/logo-mark.svg', import.meta.url).href}")`);
  const mode = await getMode();
  const top = document.createElement('div');
  top.innerHTML = `
    ${mode === 'demo' ? `<div class="demo-banner">Preview store — no backend connected. Orders & payments here are simulated. <a href="admin.html">Admin demo</a></div>` : ''}
    <div class="topbar" aria-label="Announcements" aria-live="polite"><span class="topbar__msg">${ANNOUNCEMENTS[0]}</span></div>
    <header class="site-header ${overlayHeader ? 'site-header--overlay' : ''}">
      <div class="wrap header-row">
        <button class="icon-btn burger" data-open="nav" aria-label="Menu">${icon.menu}</button>
        <a class="brand" href="index.html" aria-label="TridentWear home">${logo}<b class="wordmark">TridentWear</b></a>
        <nav class="nav" aria-label="Main">${NAV.map(([h, l, k]) => `<a href="${h}" class="${k === page ? 'is-active' : ''}">${l}</a>`).join('')}</nav>
        <div class="header-actions">
          <button class="icon-btn" data-open="search" aria-label="Search">${icon.search}</button>
          <a class="icon-btn hide-sm" href="wishlist.html" aria-label="Wishlist">${icon.heart}<span class="badge" data-badge="wish"></span></a>
          <a class="icon-btn hide-sm" href="account.html" aria-label="Account">${icon.user}</a>
          <button class="icon-btn" data-open="cart" aria-label="Bag">${icon.bag}<span class="badge" data-badge="cart"></span></button>
        </div>
      </div>
    </header>`;
  document.body.prepend(...top.children);

  const extra = document.createElement('div');
  extra.innerHTML = `
    <div class="search-panel" data-panel="search"><div class="search-box">
      <input type="search" placeholder="Search tees, shirts, colours…" aria-label="Search products" autocomplete="off">
      <div class="search-results"></div></div></div>
    <div class="drawer drawer--left" data-panel="nav"><div class="drawer__scrim" data-close></div><div class="drawer__panel">
      <div class="drawer__head"><a class="brand" href="index.html">${logo}<b class="wordmark">TridentWear</b></a><button class="icon-btn" data-close aria-label="Close">${icon.close}</button></div>
      <div class="drawer__body mobile-nav">${NAV.map(([h, l]) => `<a href="${h}">${l}<span>${icon.arrow}</span></a>`).join('')}
        <a href="account.html">Account<span>${icon.arrow}</span></a><a href="wishlist.html">Wishlist<span>${icon.arrow}</span></a><a href="contact.html">Contact<span>${icon.arrow}</span></a></div>
    </div></div>
    <div class="drawer" data-panel="cart"><div class="drawer__scrim" data-close></div><div class="drawer__panel" aria-label="Shopping bag">
      <div class="drawer__head"><b>Your bag</b><button class="icon-btn" data-close aria-label="Close">${icon.close}</button></div>
      <div class="drawer__body" data-cart-body></div><div class="drawer__foot" data-cart-foot></div>
    </div></div>
    <nav class="tabbar" aria-label="App navigation">
      <a href="index.html" class="${page === 'home' ? 'is-active' : ''}">${icon.home}Home</a>
      <a href="shop.html" class="${['shop', 'tshirt', 'shirt'].includes(page) ? 'is-active' : ''}">${icon.grid}Shop</a>
      <a href="tryon.html" class="${page === 'tryon' ? 'is-active' : ''}">${icon.camera}Fit Check</a>
      <a href="wishlist.html" class="${page === 'wishlist' ? 'is-active' : ''}">${icon.heart}Saved<span class="badge" data-badge="wish"></span></a>
      <a href="account.html" class="${page === 'account' ? 'is-active' : ''}">${icon.user}Account</a>
    </nav>`;
  document.body.append(...extra.children);
  document.body.append(footer(logo));

  // open/close panels
  document.addEventListener('click', (e) => {
    const o = e.target.closest('[data-open]');
    if (o) { e.preventDefault(); openPanel(o.dataset.open); }
    if (e.target.closest('[data-close]')) $$('.drawer.is-open, .search-panel.is-open').forEach((d) => d.classList.remove('is-open'));
  });
  $('.search-panel').addEventListener('click', (e) => { if (e.target.classList.contains('search-panel')) e.currentTarget.classList.remove('is-open'); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') $$('.drawer.is-open, .search-panel.is-open').forEach((d) => d.classList.remove('is-open')); if (e.key === '/' && !/input|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); openPanel('search'); } });
  setupSearch();

  const header = $('.site-header');
  const onScroll = () => header.classList.toggle('is-scrolled', scrollY > 10);
  onScroll(); addEventListener('scroll', onScroll, { passive: true });

  const badges = () => {
    $$('[data-badge="cart"]').forEach((b) => { b.textContent = cart.count() || ''; b.dataset.count = cart.count(); });
    $$('[data-badge="wish"]').forEach((b) => { b.textContent = wishlist.ids.length || ''; b.dataset.count = wishlist.ids.length; });
  };
  badges();
  addEventListener('tw:cart', () => { badges(); renderCartDrawer(); });
  addEventListener('tw:wish', badges);
  addEventListener('storage', badges);
  session.load();
  reveal();
  rotateAnnouncements();
  enableInstantNav();
  spinLogos();
  registerSW();
}

// Click the Trident: it spins. On the home page it also scrolls to the top; elsewhere it
// finishes the first half-turn before navigating home.
function spinLogos() {
  document.addEventListener('click', (e) => {
    const mark = e.target.closest('.brand, .studio__brand h1');
    if (!mark) return;
    const svg = mark.querySelector('svg'); if (!svg) return;
    svg.classList.remove('is-spinning'); void svg.getBoundingClientRect(); svg.classList.add('is-spinning');
    svg.addEventListener('animationend', () => svg.classList.remove('is-spinning'), { once: true });
    const a = mark.closest('a[href]');
    if (!a) return;
    const home = /(^|\/)(index\.html)?$/.test(location.pathname);
    e.preventDefault();
    if (home) scrollTo({ top: 0, behavior: 'smooth' });
    else setTimeout(() => (location.href = a.href), matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 420);
  });
}

function rotateAnnouncements() {
  let el = $('.topbar__msg');
  if (!el || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  let i = 0;
  setInterval(() => {
    if (document.hidden) return;
    i = (i + 1) % ANNOUNCEMENTS.length;
    const next = el.cloneNode(); next.innerHTML = ANNOUNCEMENTS[i];
    el.replaceWith(next); el = next; // re-insert so the entrance animation replays
  }, 5000);
}

// Instant navigation: the browser pre-renders same-site pages on hover/press (Speculation Rules),
// and cross-document View Transitions (see tw.css) cross-fade between pages.
function enableInstantNav() {
  if (HTMLScriptElement.supports?.('speculationrules') && !document.querySelector('script[type="speculationrules"]')) {
    const s = document.createElement('script');
    s.type = 'speculationrules';
    s.textContent = JSON.stringify({
      prerender: [{ where: { and: [{ href_matches: '/*' }, { not: { href_matches: '/admin*' } }, { not: { href_matches: '/*checkout*' } }] }, eagerness: 'moderate' }],
    });
    document.head.append(s);
  }
}

export function openPanel(name) {
  const el = $(`[data-panel="${name}"]`);
  if (!el) return;
  el.classList.add('is-open');
  if (name === 'search') setTimeout(() => $('input', el).focus(), 50);
  if (name === 'cart') renderCartDrawer();
}

function footer(logo) {
  const f = document.createElement('footer');
  f.className = 'site-footer';
  const b = CONFIG.brand;
  f.innerHTML = `<div class="wrap">
    <div class="footer-grid">
      <div class="footer-brand"><a class="brand" href="index.html">${logo}<b class="wordmark">TridentWear</b></a>
        <p style="max-width:34ch;margin:0">Heavyweight T-shirts and shirts, designed and made in India. Cut clean, worn hard.</p>
        <div class="socials"><a href="${b.instagram}" aria-label="Instagram" rel="noopener" target="_blank">${icon.insta}</a><a href="https://wa.me/${b.whatsapp}" aria-label="WhatsApp" rel="noopener" target="_blank">${icon.whatsapp}</a><a href="mailto:${b.email}" aria-label="Email">${icon.mail}</a></div></div>
      <div><h4>Shop</h4><a href="shop.html?cat=tshirt">T-Shirts</a><a href="shop.html?cat=shirt">Shirts</a><a href="shop.html?sort=new">New arrivals</a><a href="tryon.html">AI Fit Check</a></div>
      <div><h4>Help</h4><a href="order.html">Track order</a><a href="policies.html#shipping">Shipping</a><a href="policies.html#returns">Returns & exchanges</a><a href="faq.html">FAQ</a><a href="contact.html">Contact us</a></div>
      <div><h4>Company</h4><a href="about.html">Our story</a><a href="policies.html#privacy">Privacy</a><a href="policies.html#terms">Terms</a><a href="admin.html">Admin</a></div>
    </div>
    <div class="footer-wordmark" aria-hidden="true">TridentWear</div>
    <div class="footer-bottom"><span>© ${new Date().getFullYear()} TridentWear. All rights reserved.</span>
      <div class="pay-icons"><span>UPI</span><span>VISA</span><span>MASTERCARD</span><span>RUPAY</span><span>NETBANKING</span><span>COD</span></div></div>
  </div>`;
  return f;
}

async function setupSearch() {
  const input = $('.search-box input');
  const out = $('.search-results');
  input.addEventListener('input', async () => {
    const q = input.value.trim().toLowerCase();
    if (!q) { out.innerHTML = ''; return; }
    const list = (await getProducts()).filter((p) => [p.name, p.base_color, p.category, p.tag, p.fit_type].join(' ').toLowerCase().includes(q)).slice(0, 8);
    out.innerHTML = list.length ? list.map((p) => `<a href="product.html?id=${p.id}"><img src="${img(p.image)}" alt=""><span><b>${esc(p.name)}</b><br><small class="muted">${esc(p.base_color)} · ${inr(p.price)}</small></span></a>`).join('')
      : `<p class="muted" style="padding:12px">No matches for “${esc(q)}”.</p>`;
  });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') location.href = `shop.html?q=${encodeURIComponent(input.value.trim())}`; });
}

export async function renderCartDrawer() {
  const body = $('[data-cart-body]'); const foot = $('[data-cart-foot]');
  if (!body) return;
  const { lines, subtotal, savings } = await cart.detailed();
  if (!lines.length) {
    body.innerHTML = `<div class="empty">${icon.bag}<b>Your bag is empty</b><p class="muted">Add a tee or shirt and it will show up here.</p><a class="btn" href="shop.html">Browse the shop</a></div>`;
    foot.innerHTML = ''; return;
  }
  body.innerHTML = lines.map(lineHtml).join('');
  foot.innerHTML = `<div class="totals"><div><span>Subtotal</span><b>${inr(subtotal)}</b></div>${savings ? `<div class="muted"><span>You save</span><span>${inr(savings)}</span></div>` : ''}<div class="muted"><span>Shipping</span><span>Free</span></div></div>
    <a class="btn btn--block" href="checkout.html">Checkout · ${inr(subtotal)}</a><a class="btn btn--ghost btn--block" href="cart.html">View bag</a>`;
}
export function lineHtml(l) {
  const p = l.product;
  return `<div class="line" data-line="${p.id}|${esc(l.size)}">
    <a class="line__img" href="product.html?id=${p.id}"><img src="${img(p.image)}" alt=""></a>
    <div><div class="line__name">${esc(p.name)}</div><div class="line__meta">${esc(p.base_color || '')} · Size ${esc(l.size)}</div>
      <div class="qty"><button data-qty="-1" aria-label="Decrease">−</button><input value="${l.qty}" readonly aria-label="Quantity"><button data-qty="1" aria-label="Increase">+</button></div>
      <button class="line__remove" data-remove>Remove</button></div>
    <b>${inr(p.price * l.qty)}</b></div>`;
}
document.addEventListener('click', (e) => {
  const line = e.target.closest('[data-line]');
  if (!line) return;
  const [id, size] = line.dataset.line.split('|');
  const item = cart.items.find((i) => i.id === Number(id) && i.size === size);
  if (!item) return;
  if (e.target.closest('[data-qty]')) cart.setQty(item.id, size, item.qty + Number(e.target.closest('[data-qty]').dataset.qty));
  if (e.target.closest('[data-remove]')) cart.remove(item.id, size);
});

// ---------------------------------------------------------------- PWA
function registerSW() {
  if (!('serviceWorker' in navigator) || location.protocol === 'file:') return;
  // When an updated service worker takes over a page that an older one served, reload once
  // so the page never runs a mix of old and new code.
  const hadController = !!navigator.serviceWorker.controller;
  let reloaded = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController || reloaded) return;
    reloaded = true; location.reload();
  });
  addEventListener('load', () => navigator.serviceWorker.register('sw.js').then((r) => r.update()).catch(() => {}));
}
