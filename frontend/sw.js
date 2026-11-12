// TridentWear service worker — offline shell + fast repeat visits.
// Strategy: pages, CSS, JS and data = network-first (so a deploy shows up on the next load, not the one after);
// images and fonts = cache-first with background refresh; API = network only (never cache prices, stock, auth, payments).
const VERSION = 'tw-v5';
const SHELL = [
  './', 'index.html', 'shop.html', 'product.html', 'cart.html', 'offline.html',
  'assets/css/tw.css', 'assets/js/ui.js', 'assets/js/api.js', 'assets/js/demo.js', 'assets/js/store.js', 'assets/js/config.js',
  'assets/brand/logo-mark.svg', 'assets/brand/favicon.svg', 'assets/fonts/bricolage.woff2', 'assets/brand/icon-192.png', 'assets/data/products.json',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return; // Razorpay, CDN, fonts: browser default
  if (url.pathname.includes('/api/')) return; // never cache API

  const networkFirst = req.mode === 'navigate' || /\.(css|js|json|webmanifest)$/.test(url.pathname);
  if (networkFirst) {
    e.respondWith(fetch(req.mode === 'navigate' ? req : new Request(req, { cache: 'no-cache' })).then((res) => { caches.open(VERSION).then((c) => c.put(req, res.clone())); return res; })
      .catch(async () => (await caches.match(req)) || (req.mode === 'navigate' ? caches.match('offline.html') : Response.error())));
    return;
  }
  e.respondWith(caches.match(req).then((hit) => {
    const net = fetch(req).then((res) => { if (res.ok) caches.open(VERSION).then((c) => c.put(req, res.clone())); return res; }).catch(() => hit);
    return hit || net;
  }));
});
