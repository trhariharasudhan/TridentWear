// End-to-end smoke test of the storefront.
//   BASE=http://127.0.0.1:8020 ADMIN_EMAIL=admin@trident.local ADMIN_PASSWORD=Admin@12345 node tests/e2e/smoke.mjs
// Works against the FastAPI backend ("live") or a static build ("demo": BASE=http://localhost:8811 DEMO=1).
// Optional: CHROME_PATH=/path/to/chrome, SHOTS=dir to save screenshots.
import { chromium } from 'playwright';
import fs from 'node:fs';

const BASE = (process.env.BASE || 'http://127.0.0.1:8020').replace(/\/$/, '');
const DEMO = process.env.DEMO === '1';
const ADMIN = DEMO ? ['admin@tridentwear.in', 'Admin@123'] : [process.env.ADMIN_EMAIL || 'admin@trident.local', process.env.ADMIN_PASSWORD || 'Admin@12345'];
const SHOTS = process.env.SHOTS;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

const results = [];
const errors = [];
async function step(name, fn) {
  const t = Date.now();
  try { await fn(); results.push(['PASS', name, Date.now() - t]); }
  catch (e) { results.push(['FAIL', name, Date.now() - t, e.message.split('\n')[0]]); }
}
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});

async function newPage(opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, ...opts });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(`${page.url()} :: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|fonts\.g|ERR_INTERNET|ERR_NAME|ERR_CONNECTION|net::ERR|Failed to load resource/i.test(m.text())) errors.push(`${page.url()} :: console: ${m.text()}`); });
  return page;
}
const shot = async (page, name) => SHOTS && page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
const expect = (cond, msg) => { if (!cond) throw new Error(msg); };

const page = await newPage();
await step('home renders hero rail + featured products', async () => {
  await page.goto(`${BASE}/index.html`, { waitUntil: 'networkidle' });
  await page.waitForSelector('.piece__front');
  expect((await page.locator('.piece').count()) >= 8, 'studio rail pieces missing');
  await page.waitForSelector('[data-featured] .card');
  if (DEMO) expect(await page.locator('.demo-banner').isVisible(), 'demo banner missing');
  await shot(page, '01-home');
});

await step('shop filters by category and size', async () => {
  await page.goto(`${BASE}/shop.html?cat=shirt`, { waitUntil: 'networkidle' });
  await page.waitForSelector('.grid .card');
  const shirts = await page.locator('.grid .card').count();
  expect(shirts > 0 && shirts < 16, `unexpected shirt count ${shirts}`);
  await page.click('.chip[data-k="cat"][data-v="tshirt"]');
  expect((await page.locator('.grid .card').count()) > 0, 'no tees');
  await shot(page, '02-shop');
});

await step('product: size required, then add to bag', async () => {
  await page.goto(`${BASE}/product.html?id=2`, { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-add]');
  await page.click('[data-add]');
  expect((await page.textContent('[data-size-error]')).includes('size'), 'missing size validation');
  await page.click('[data-size="L"]');
  await page.click('[data-add]');
  await page.waitForSelector('.toast');
  expect((await page.textContent('[data-badge="cart"]')).trim() === '1', 'cart badge not updated');
  await shot(page, '03-product');
});

await step('cart applies TRIDENTFIRST coupon', async () => {
  await page.goto(`${BASE}/cart.html`, { waitUntil: 'networkidle' });
  await page.fill('#coupon', 'TRIDENTFIRST');
  await page.click('[data-apply]');
  await page.waitForSelector('text=applied');
  const total = await page.textContent('.grand');
  expect(/719\.2|719/.test(total), `expected 20% off 899 → 719.2, got ${total}`);
});

const fillCheckout = async (p) => {
  await p.fill('[name=name]', 'Test Shopper');
  await p.fill('[name=phone]', '9876543210');
  await p.fill('[name=email]', 'shopper@example.com');
  await p.fill('[name=address]', '12 MG Road, Indiranagar');
  await p.fill('[name=pincode]', '560038');
  await p.fill('[name=city]', 'Bengaluru');
  await p.selectOption('[name=state]', 'Karnataka');
};

let codOrder = '';
await step('checkout with Cash on Delivery creates an order', async () => {
  await page.goto(`${BASE}/checkout.html`, { waitUntil: 'networkidle' });
  await page.click('[data-place]');
  expect((await page.textContent('[data-error]')).length > 0, 'empty form was accepted');
  await fillCheckout(page);
  await page.check('input[name=method][value=cod]');
  await shot(page, '04-checkout');
  await page.click('[data-place]');
  await page.waitForURL(/order\.html\?id=TRD-/, { timeout: 15000 });
  codOrder = new URL(page.url()).searchParams.get('id');
  await page.waitForSelector('text=Order confirmed');
  await shot(page, '05-order');
});

await step('online payment (simulated gateway) verifies and places order', async () => {
  await page.goto(`${BASE}/product.html?id=11`, { waitUntil: 'networkidle' });
  await page.click('[data-size="M"]'); await page.click('[data-add]');
  await page.goto(`${BASE}/checkout.html`, { waitUntil: 'networkidle' });
  await fillCheckout(page);
  await page.click('[data-place]');
  await page.waitForSelector('[data-ok]', { timeout: 15000 });
  await shot(page, '06-paysheet');
  await page.click('[data-ok]');
  await page.waitForURL(/order\.html\?id=TRD-/, { timeout: 15000 });
});

await step('payment failure keeps the bag and shows an error', async () => {
  await page.goto(`${BASE}/product.html?id=1`, { waitUntil: 'networkidle' });
  await page.click('[data-size="S"]'); await page.click('[data-add]');
  await page.goto(`${BASE}/checkout.html`, { waitUntil: 'networkidle' });
  await fillCheckout(page);
  await page.click('[data-place]');
  await page.waitForSelector('[data-fail]');
  await page.click('[data-fail]');
  await page.waitForFunction(() => document.querySelector('[data-error]')?.textContent.includes('failed'));
  expect((await page.textContent('[data-badge="cart"]')).trim() === '1', 'bag was cleared after failed payment');
});

await step('order tracking page finds the COD order', async () => {
  await page.goto(`${BASE}/order.html?id=${codOrder}`, { waitUntil: 'networkidle' });
  await page.waitForSelector('.timeline');
});

const email = `e2e${Date.now()}@example.com`;
await step('register → email OTP verify → signed in → orders tab', async () => {
  const p = await newPage();
  await p.goto(`${BASE}/account.html#register`, { waitUntil: 'networkidle' });
  await p.fill('[name=name]', 'E2E User'); await p.fill('[name=email]', email); await p.fill('[name=password]', 'Trident123');
  await p.check('[name=terms]');
  await p.click('[data-reg] button.btn');
  await p.waitForSelector('[data-verify]');
  const code = (await p.textContent('.dev-hint b')).trim();
  const boxes = p.locator('.otp input');
  for (let i = 0; i < 6; i++) await boxes.nth(i).fill(code[i]);
  await p.click('[data-verify] button.btn');
  await p.waitForSelector('[data-sec="orders"].is-on', { timeout: 10000 });
  await shot(p, '07-account');
  await p.context().close();
});

await step('account dashboard: add address, it pre-fills checkout', async () => {
  const p = await newPage();
  await p.goto(`${BASE}/account.html#register`, { waitUntil: 'networkidle' });
  const em = `addr${Date.now()}@example.com`;
  await p.fill('[name=name]', 'Address Tester'); await p.fill('[name=email]', em); await p.fill('[name=password]', 'Trident123');
  await p.check('[name=terms]'); await p.click('[data-reg] button.btn');
  await p.waitForSelector('[data-verify]');
  const code = (await p.textContent('.dev-hint b')).trim();
  const boxes = p.locator('.otp input');
  for (let i = 0; i < 6; i++) await boxes.nth(i).fill(code[i]);
  await p.click('[data-verify] button.btn');
  await p.waitForSelector('.profile-hero');
  expect((await p.locator('.stat').count()) === 4, 'stat tiles missing');
  await p.click('[data-sec="addresses"]');
  await p.click('[data-add-addr]');
  await p.fill('[data-addr] [name=pin]', '560068');
  await p.fill('[data-addr] [name=street]', '12 MG Road, 2nd Cross');
  await p.fill('[data-addr] [name=city]', 'Bengaluru');
  await p.selectOption('[data-addr] [name=state]', 'Karnataka');
  await p.click('[data-addr] button.btn');
  await p.waitForSelector('.addr.is-default');
  expect((await p.textContent('.addr')).includes('560068'), 'saved address not listed');
  // a returning, signed-in visitor (page reload) must get the dashboard, not a blank page
  await p.reload({ waitUntil: 'networkidle' });
  await p.waitForSelector('.profile-hero', { timeout: 8000 });
  await p.click('[data-sec="profile"]'); await p.waitForSelector('[data-prefs]');
  await p.fill('[data-prof] [name=birthday]', '1999-05-17'); await p.click('[data-prof] button.btn'); await p.waitForTimeout(500);
  await p.check('[name=order_updates_whatsapp]', { force: true }); await p.waitForTimeout(700);
  await p.reload({ waitUntil: 'networkidle' }); await p.waitForSelector('[data-prefs]');
  expect((await p.inputValue('[data-prof] [name=birthday]')) === '1999-05-17', 'birthday not saved');
  expect(await p.isChecked('[name=order_updates_whatsapp]'), 'notification preference not saved');
  await shot(p, '07b-account-addresses');
  await p.click('[data-sec="size"]');
  await p.fill('[data-size-form] [name=height]', '175'); await p.fill('[data-size-form] [name=weight]', '72');
  await p.click('[data-size-form] button');
  expect((await p.textContent('.size-result b')).trim() === 'L', 'size estimate wrong');
  // checkout picks up the default address
  await p.goto(`${BASE}/product.html?id=3`, { waitUntil: 'networkidle' });
  await p.click('[data-size="M"]'); await p.click('[data-add]');
  await p.evaluate(() => localStorage.removeItem('tw_last_address'));
  await p.goto(`${BASE}/checkout.html`, { waitUntil: 'networkidle' });
  await p.waitForSelector('[name=pincode]');
  expect((await p.inputValue('[name=pincode]')) === '560068', 'checkout did not pre-fill default address');
  expect((await p.inputValue('[name=city]')) === 'Bengaluru', 'checkout city not pre-filled');
  await p.context().close();
});

await step('studio rail: page scroll does not move it; arrows, drag and twist do', async () => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 }, reducedMotion: 'reduce' }); // no idle drift
  const p = await ctx.newPage();
  await p.goto(`${BASE}/index.html`, { waitUntil: 'networkidle' });
  await p.waitForFunction(() => window.__studio);
  const off = () => p.evaluate(() => Math.round(window.__studio.offset));
  const before = await off();
  await p.mouse.wheel(0, 600); await p.waitForTimeout(400);
  expect((await off()) === before, 'rail moved on vertical page scroll');
  await p.evaluate(() => scrollTo(0, 0)); await p.waitForTimeout(200);
  await p.click('[data-rail-step="1"]'); await p.waitForTimeout(900);
  const afterArrow = await off();
  expect(afterArrow < before, `next arrow did not move the rail (${before} -> ${afterArrow})`);
  // drag the rail by hand
  const box = await p.locator('[data-stage]').boundingBox();
  const y = box.y + box.height * 0.9;
  await p.mouse.move(box.x + box.width / 2, y); await p.mouse.down();
  for (let i = 1; i <= 10; i++) await p.mouse.move(box.x + box.width / 2 - i * 20, y);
  await p.mouse.up(); await p.waitForTimeout(300);
  expect((await off()) < afterArrow - 100, 'dragging did not move the rail');
  // loop: travel far, the screen is still full of pieces
  for (let i = 0; i < 40; i++) await p.evaluate(() => window.__studio.step(1));
  await p.waitForTimeout(1500);
  const visible = await p.evaluate(() => [...document.querySelectorAll('.piece')].filter((e) => { const r = e.getBoundingClientRect(); return r.right > 0 && r.left < innerWidth; }).length);
  expect(visible >= 4, `rail did not loop (${visible} visible)`);
  // a plain click still opens the product
  await p.locator('.piece').filter({ has: p.locator('.piece__front') }).nth(2).evaluate((a) => a.click());
  await p.waitForURL(/product\.html\?id=/);
  await ctx.close();
});

await step('admin storefront editor changes the live site', async () => {
  const p = await newPage();
  await p.goto(`${BASE}/account.html?next=admin.html`, { waitUntil: 'networkidle' });
  await p.fill('[name=email]', ADMIN[0]); await p.fill('[name=password]', ADMIN[1]);
  await p.click('[data-login] button.btn');
  await p.waitForURL(/admin\.html/); await p.waitForSelector('.kpi');
  await p.click('[data-go="storefront"]');
  await p.waitForSelector('[data-site]');
  await p.fill('[data-site] [name=hero_line]', 'E2E line // Drop 02 soon');
  await p.fill('[data-site] [name=announcements]', 'E2E announcement with CODE2026');
  await p.click('[data-save]');
  await p.waitForSelector('.toast');
  await p.evaluate(() => sessionStorage.clear());
  await p.goto(`${BASE}/index.html`, { waitUntil: 'networkidle' });
  expect((await p.textContent('.studio__line')).includes('E2E line'), 'hero line not updated');
  expect((await p.textContent('.topbar')).includes('E2E announcement'), 'announcement not updated');
  expect((await p.innerHTML('.topbar')).includes('<b>CODE2026</b>'), 'code not bolded');
  await p.context().close();
});

await step('admin: dashboard, products, update order status', async () => {
  const p = await newPage();
  await p.goto(`${BASE}/account.html?next=admin.html`, { waitUntil: 'networkidle' });
  await p.fill('[name=email]', ADMIN[0]); await p.fill('[name=password]', ADMIN[1]);
  await p.click('[data-login] button.btn');
  await p.waitForURL(/admin\.html/);
  await p.waitForSelector('.kpi');
  await shot(p, '08-admin-dashboard');
  await p.click('[data-go="products"]'); await p.waitForSelector('[data-edit]');
  await p.click('[data-go="orders"]'); await p.waitForSelector('[data-manage]');
  await p.click(`[data-manage="${codOrder}"]`);
  await p.selectOption('[data-of] [name=status]', 'shipped');
  await p.fill('[data-of] [name=tracking_id]', 'DLV123456');
  await p.fill('[data-of] [name=courier]', 'Delhivery');
  await p.click('[data-of] button.btn');
  await p.waitForSelector('text=Order updated');
  await shot(p, '09-admin-orders');
  const t = await newPage();
  await t.goto(`${BASE}/order.html?id=${codOrder}`, { waitUntil: 'networkidle' });
  await t.waitForSelector('text=DLV123456');
  await p.context().close(); await t.context().close();
});

await step('AI Fit Check: photo upload renders garment + snapshot', async () => {
  const p = await newPage({ viewport: { width: 1280, height: 900 } });
  await p.goto(`${BASE}/tryon.html?id=7`, { waitUntil: 'networkidle' });
  await p.waitForSelector('[data-pick].is-on');
  // synthesise a simple "photo" so the test needs no fixtures
  const dataUrl = await p.evaluate(() => { const c = document.createElement('canvas'); c.width = 600; c.height = 800; const x = c.getContext('2d'); x.fillStyle = '#c9ccd2'; x.fillRect(0, 0, 600, 800); x.fillStyle = '#6b6f78'; x.beginPath(); x.arc(300, 170, 70, 0, 7); x.fill(); x.fillRect(170, 250, 260, 520); return c.toDataURL('image/png'); });
  await p.setInputFiles('[data-upload]', { name: 'me.png', mimeType: 'image/png', buffer: Buffer.from(dataUrl.split(',')[1], 'base64') });
  await p.waitForFunction(() => !/Analysing/.test(document.querySelector('[data-status]').textContent), null, { timeout: 30000 });
  const painted = await p.evaluate(() => { const c = document.querySelector('[data-canvas]'); const d = c.getContext('2d').getImageData(c.width / 2, c.height * 0.45, 1, 1).data; return [...d]; });
  expect(painted[3] > 0, 'canvas not painted');
  await p.click('[data-snap]');
  await p.waitForSelector('.shot img');
  await shot(p, '10-tryon');
  await p.context().close();
});

await step('mobile layout shows app tab bar', async () => {
  const p = await newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  await p.goto(`${BASE}/index.html`, { waitUntil: 'networkidle' });
  expect(await p.locator('.tabbar').isVisible(), 'tab bar hidden on mobile');
  await shot(p, '11-mobile-home');
  await p.goto(`${BASE}/product.html?id=5`, { waitUntil: 'networkidle' });
  expect(await p.locator('[data-sticky]').isVisible(), 'sticky buy bar hidden');
  await shot(p, '12-mobile-product');
  await p.context().close();
});

await browser.close();
for (const [s, n, ms, err] of results) console.log(`${s === 'PASS' ? '✔' : '✘'} ${n} (${ms}ms)${err ? `\n    → ${err}` : ''}`);
if (errors.length) { console.log('\nJS errors:'); [...new Set(errors)].forEach((e) => console.log('  ' + e)); }
const failed = results.filter((r) => r[0] === 'FAIL').length;
console.log(`\n${results.length - failed}/${results.length} passed${errors.length ? `, ${new Set(errors).size} JS errors` : ''}`);
process.exit(failed || errors.length ? 1 : 0);
