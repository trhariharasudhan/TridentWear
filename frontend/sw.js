// TridentWear service worker — offline shell + fast repeat visits.
// Strategy: pages = network-first (fallback cache/offline), static assets = stale-while-revalidate,
// API = network only (never cache prices, stock, auth or payments).
const VERSION = 'tw-v1';
const SHELL = [
  './', 'index.html', 'shop.html', 'product.html', 'cart.html', 'offline.html',
  'assets/css/tw.css', 'assets/js/ui.js', 'assets/js/api.js', 'assets/js/demo.js', 'assets/js/store.js', 'assets/js/config.js',
  'assets/brand/logo-mark.svg', 'assets/brand/favicon.svg', 'assets/brand/icon-192.png', 'assets/data/products.json',
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

  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then((res) => { caches.open(VERSION).then((c) => c.put(req, res.clone())); return res; })
      .catch(async () => (await caches.match(req)) || caches.match('offline.html')));
    return;
  }
  e.respondWith(caches.match(req).then((hit) => {
    const net = fetch(req).then((res) => { if (res.ok) caches.open(VERSION).then((c) => c.put(req, res.clone())); return res; }).catch(() => hit);
    return hit || net;
  }));
});
