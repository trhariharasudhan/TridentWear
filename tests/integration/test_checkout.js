const playwright = require('playwright');
(async () => {
  const BASE_URL = process.env.TRIDENT_BASE_URL || 'http://127.0.0.1:8020';
  const browser = await playwright.chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));

  // ── STEP: Login ────────────────────────────────────────────────
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(800);
  await page.fill('#login-email', 'customer@trident.local');
  await page.fill('#login-password', 'password');
  await page.click('button[type=submit]');
  await page.waitForTimeout(2000);
  console.log('After login URL:', page.url());

  // ── STEP: Inject cart for user ID 2 ──────────────────────────
  await page.evaluate(() => {
    localStorage.setItem('trident-cart-2', JSON.stringify([
      { id: 1, name: 'Classic Black Crew Neck', price: 799, qty: 1, size: 'M', image: '/images/black-tshirt.png' }
    ]));
  });

  // ── STEP: Checkout ─────────────────────────────────────────────
  await page.goto(`${BASE_URL}/checkout`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);

  const cartSummaryText = await page.evaluate(() => {
    const el = document.querySelector('[data-cart-summary]');
    return el ? el.innerText : 'NOT FOUND';
  });
  console.log('Cart summary:', cartSummaryText);

  await page.fill('#checkout-name', 'Test Buyer');
  await page.fill('#checkout-email', 'customer@trident.local');
  await page.fill('#checkout-phone', '9876543210');
  await page.fill('#checkout-city', 'Mumbai');
  await page.fill('#checkout-address', '123 Marine Drive');
  await page.fill('#checkout-postal', '400001');

  // Force-check COD (it is inside a CSS-styled label, so not directly clickable)
  await page.evaluate(() => {
    const cod = document.querySelector('input[name=payment][value=cod]');
    if (cod) cod.checked = true;
  });

  // Submit
  const btn = await page.$('[data-checkout-button]');
  if (!btn) {
    console.log('ERROR: No checkout button found');
    await browser.close();
    return;
  }
  await btn.click();
  await page.waitForTimeout(5000);

  const body = await page.evaluate(() => document.body.innerText);
  const hasSuccess = body.includes('TRD-') || body.includes('Order Placed') || body.includes('placed successfully');
  console.log('Checkout success:', hasSuccess);
  const orderIdMatch = body.match(/TRD-[A-Z0-9]+/);
  if (orderIdMatch) {
    console.log('Order ID found:', orderIdMatch[0]);
  } else {
    console.log('Body (first 500):', body.substring(0, 500));
  }

  // ── STEP: Profile orders ─────────────────────────────────────
  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);

  // Click on My Orders tab to make orders visible in innerText
  const ordersTab = await page.$('[data-tab="orders"]');
  if (ordersTab) {
    await ordersTab.click();
    await page.waitForTimeout(1000);
  }

  const profileText = await page.evaluate(() => document.body.innerText);
  const orders = profileText.match(/TRD-[A-Z0-9]+/g) || [];
  console.log('Orders in profile:', orders.length, orders.join(', '));

  console.log('Page errors:', errors);
  await browser.close();
})();
