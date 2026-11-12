// Build the static storefront for GitHub Pages into frontend/dist.
// The site is plain HTML/CSS/ES modules, so "build" = validate + copy + sitemap.
//   npm run build
// Set TW_API_BASE to point the static site at a hosted backend, e.g.
//   TW_API_BASE=https://tridentwear-api.onrender.com npm run build
const fs = require('fs');
const path = require('path');

const SRC = path.resolve(__dirname, '../frontend');
const OUT = path.join(SRC, 'dist');
const SITE = process.env.TW_SITE_URL || 'https://trhariharasudhan.github.io/TridentWear';
const API_BASE = (process.env.TW_API_BASE || '').replace(/\/$/, '');
const fail = (m) => { console.error(`\n[build] ERROR: ${m}`); process.exit(1); };

// ---- validate catalog
const products = JSON.parse(fs.readFileSync(path.join(SRC, 'assets/data/products.json'), 'utf8'));
const ids = new Set();
for (const [i, p] of products.entries()) {
  if (ids.has(p.id)) fail(`duplicate product id ${p.id} at index ${i}`);
  ids.add(p.id);
  for (const k of ['name', 'category', 'price', 'image']) if (p[k] === undefined || p[k] === '') fail(`product ${p.id} missing "${k}"`);
  for (const im of p.gallery || [p.image]) {
    const file = path.join(SRC, 'assets/images', im.replace(/^\/images\//, ''));
    if (!fs.existsSync(file)) fail(`product ${p.id} image not found: ${im}`);
  }
}

// ---- copy
fs.rmSync(OUT, { recursive: true, force: true });
const copy = (from, to) => {
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    if (entry.name === 'dist' || entry.name.startsWith('.')) continue;
    const a = path.join(from, entry.name), b = path.join(to, entry.name);
    if (entry.isDirectory()) { fs.mkdirSync(b, { recursive: true }); copy(a, b); } else fs.copyFileSync(a, b);
  }
};
fs.mkdirSync(OUT, { recursive: true });
copy(SRC, OUT);
fs.writeFileSync(path.join(OUT, '.nojekyll'), '');

// ---- inject API base (optional) into every page
const pages = fs.readdirSync(OUT).filter((f) => f.endsWith('.html'));
if (API_BASE) {
  for (const f of pages) {
    const file = path.join(OUT, f);
    fs.writeFileSync(file, fs.readFileSync(file, 'utf8').replace('<head>', `<head>\n  <script>window.TW_API_BASE=${JSON.stringify(API_BASE)};</script>`));
  }
}

// ---- sitemap
const urls = ['', 'shop.html', 'shop.html?cat=tshirt', 'shop.html?cat=shirt', 'tryon.html', 'about.html', 'faq.html', 'contact.html', 'policies.html',
  ...products.map((p) => `product.html?id=${p.id}`)];
const sitemap = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map((u) => `  <url><loc>${SITE}/${u.replace(/&/g, '&amp;')}</loc></url>`).join('\n')}\n</urlset>\n`;
fs.writeFileSync(path.join(OUT, 'sitemap.xml'), sitemap);
fs.writeFileSync(path.join(SRC, 'sitemap.xml'), sitemap);

console.log(`[build] ${products.length} products OK · ${pages.length} pages · api=${API_BASE || '(demo / same-origin)'} -> ${path.relative(process.cwd(), OUT)}`);
