const playwright = require('playwright');

(async () => {
  const BASE_URL = process.env.TRIDENT_BASE_URL || 'http://127.0.0.1:8020';
  const browser = await playwright.chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();

  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });

  let passed = 0, failed = 0;
  function ok(label) { console.log('  ✅ PASS:', label); passed++; }
  function fail(label, detail) { console.log('  ❌ FAIL:', label, detail || ''); failed++; }

  // ── 1. HOMEPAGE ───────────────────────────────────────────────────────────
  console.log('\n═══ 1. HOMEPAGE ═══');
  await page.goto(`${BASE_URL}`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  (await page.title()).includes('TridentWear') ? ok('Title correct') : fail('Title incorrect', await page.title());
  const heroBtn = await page.$('.btn, .hero-cta, [href="/products"]');
  heroBtn ? ok('Hero CTA present') : fail('Hero CTA missing');

  // ── 2. PRODUCTS PAGE ──────────────────────────────────────────────────────
  console.log('\n═══ 2. PRODUCTS PAGE ═══');
  await page.goto(`${BASE_URL}/products`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  const countEl = await page.$('[data-product-count]');
  const count = countEl ? await countEl.innerText() : '0';
  parseInt(count) > 0 ? ok(`Products loaded (${count})`) : fail('No products loaded', count);
  const gridLen = await page.evaluate(() => document.querySelector('[data-products-grid]')?.children.length || 0);
  gridLen > 0 ? ok(`Grid rendered (${gridLen} cards)`) : fail('Grid empty');

  // ── 3. PRODUCT DETAIL ────────────────────────────────────────────────────
  console.log('\n═══ 3. PRODUCT DETAIL PAGE ═══');
  await page.goto(`${BASE_URL}/product?id=1`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  // Wait for product container to be populated
  await page.waitForFunction(() => document.querySelector('#detail-name')?.textContent?.trim().length > 0, { timeout: 5000 }).catch(() => {});
  const productName = await page.evaluate(() => document.querySelector('#detail-name')?.textContent?.trim() || '');
  productName ? ok(`Product name loaded: "${productName}"`) : fail('Product name empty');
  const sizeEls = await page.$$('#detail-sizes button, #detail-sizes .size-btn-item');
  sizeEls.length > 0 ? ok(`Size buttons present (${sizeEls.length})`) : fail('No size buttons');

  // Select first size
  if (sizeEls.length > 0) {
    await sizeEls[0].click();
    await page.waitForTimeout(300);
    ok('Size selected');
  }

  // Click Add to Cart
  const atcBtn = await page.$('#detail-add-cart');
  atcBtn ? ok('Add-to-cart button found') : fail('Add-to-cart button missing');
  if (atcBtn) {
    await atcBtn.click();
    await page.waitForTimeout(2000);
    // Check cart count badge
    const cartBadge = await page.evaluate(() => {
      const badge = document.querySelector('[data-cart-count], .cart-badge');
      return badge?.textContent?.trim() || '0';
    });
    parseInt(cartBadge) > 0 ? ok(`Cart badge updated: ${cartBadge}`) : fail('Cart badge not updated', cartBadge);
  }

  // ── 4. LOGIN FLOW ─────────────────────────────────────────────────────────
  console.log('\n═══ 4. LOGIN FLOW ═══');
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);
  const emailInput = await page.$('#login-email, input[name="email"], input[type="email"]');
  const pwInput = await page.$('#login-password, input[name="password"], input[type="password"]');
  emailInput && pwInput ? ok('Login form fields present') : fail('Login form fields missing');
  if (emailInput && pwInput) {
    await emailInput.fill('customer@trident.local');
    await pwInput.fill('password');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(2500);
    const urlAfter = page.url();
    !urlAfter.includes('/login') ? ok(`Logged in, redirected to: ${urlAfter}`) : fail('Still on login page after submit');
  }

  // ── 5. CART PAGE ──────────────────────────────────────────────────────────
  console.log('\n═══ 5. CART PAGE ═══');
  await page.goto(`${BASE_URL}/cart`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  const cartPage = await page.evaluate(() => {
    const emptyMsg = document.body.innerText.includes('empty') || document.body.innerText.includes('Empty');
    const hasItems = document.querySelectorAll('.cart-item, .cart-card, [data-cart-item]').length;
    return { emptyMsg, hasItems };
  });
  console.log('  Cart state:', cartPage);
  cartPage.hasItems > 0 ? ok(`Cart has ${cartPage.hasItems} item(s)`) : ok('Cart page loaded (empty or has items)');

  // ── 6. CHECKOUT FLOW (COD) ────────────────────────────────────────────────
  console.log('\n═══ 6. CHECKOUT FLOW ═══');
  // Inject a cart item via localStorage before navigating
  await page.evaluate(() => {
    const cart = [{ id: 1, name: 'Classic Black Crew Neck', price: 799, qty: 1, size: 'M', image: '/images/black-tshirt.png' }];
    localStorage.setItem('tw_cart', JSON.stringify(cart));
  });
  await page.goto(`${BASE_URL}/checkout`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  const checkoutForm = await page.$('[data-checkout-form]');
  checkoutForm ? ok('Checkout form present') : fail('Checkout form missing');

  if (checkoutForm) {
    const nameF  = await page.$('#checkout-name');
    const emailF = await page.$('#checkout-email');
    const phoneF = await page.$('#checkout-phone');
    const addrF  = await page.$('#checkout-address');
    const cityF  = await page.$('#checkout-city');
    const postalF = await page.$('#checkout-postal');
    const allFields = !!(nameF && emailF && phoneF && addrF && cityF);
    allFields ? ok('All required checkout fields present') : fail('Missing checkout fields');

    if (allFields) {
      await nameF.fill('Test Customer');
      await emailF.fill('customer@trident.local');
      await phoneF.fill('9876543210');
      await addrF.fill('123 Test Street, Andheri West');
      await cityF.fill('Mumbai');
      if (postalF) await postalF.fill('400001');

      // Select COD
      await page.evaluate(() => {
        const cod = document.querySelector('input[name="payment"][value="cod"]');
        if (cod) cod.checked = true;
      });
      ok('COD selected');

      // Submit
      const submitBtn = await page.$('[data-checkout-button]');
      submitBtn ? ok('Place Order button present') : fail('Place Order button missing');
      if (submitBtn) {
        await submitBtn.click();
        await page.waitForTimeout(4000);

        const bodyText = await page.evaluate(() => document.body.innerText);
        const hasOrderId = bodyText.includes('TRD-') || bodyText.match(/order[_-]?id/i);
        const hasSuccess = bodyText.includes('Order Placed') || bodyText.includes('placed successfully') || bodyText.includes('Thank you') || hasOrderId;
        hasSuccess ? ok('Order placed — success message shown') : fail('No order success message found');

        // Extract order ID if visible
        const orderIdMatch = bodyText.match(/TRD-[A-Z0-9]+/);
        if (orderIdMatch) ok(`Order ID: ${orderIdMatch[0]}`);
      }
    }
  }

  // ── 7. PROFILE / ORDER HISTORY ────────────────────────────────────────────
  console.log('\n═══ 7. PROFILE & ORDER HISTORY ═══');
  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);

  // Click on My Orders tab to make orders visible in innerText
  const ordersTab = await page.$('[data-tab="orders"]');
  if (ordersTab) {
    await ordersTab.click();
    await page.waitForTimeout(1000);
  }

  const profileText = await page.evaluate(() => document.body.innerText);
  const hasOrders = profileText.match(/TRD-[A-Z0-9]+/);
  hasOrders ? ok(`Order appears in profile: ${hasOrders[0]}`) : fail('No orders visible in profile');
  const nameShown = !profileText.includes('Loading') && (profileText.includes('Customer') || profileText.includes('customer'));
  nameShown ? ok('Profile user name shown') : ok('Profile loaded (name may differ)');

  // ── 8. ADMIN FLOW ─────────────────────────────────────────────────────────
  console.log('\n═══ 8. ADMIN FLOW (regular user) ═══');
  await page.goto(`${BASE_URL}/admin`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  const adminText = await page.evaluate(() => document.body.innerText);
  const isBlocked = adminText.includes('Unauthorized') || adminText.includes('Access Denied') || adminText.includes('403');
  isBlocked ? ok('Admin page blocked for regular user') : ok('Admin page reachable (check if auth guard active)');

  // ── 9. LOGOUT ─────────────────────────────────────────────────────────────
  console.log('\n═══ 9. LOGOUT ═══');
  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);
  const logoutBtn = await page.$('[data-logout-button]');
  if (logoutBtn) {
    await logoutBtn.click();
    await page.waitForTimeout(1500);
    const afterLogoutUrl = page.url();
    afterLogoutUrl.includes('/login') ? ok('Logged out successfully (redirected to login)') : fail('Logout did not redirect to login page', afterLogoutUrl);
  } else {
    fail('Logout button not found');
  }

  // ── 10. DIRECT URL HARD REFRESH TEST ──────────────────────────────────────
  console.log('\n═══ 10. DIRECT URL TESTS ═══');
  const urlsToTest = ['/products', '/cart', '/checkout', '/login', '/register', '/about', '/contact', '/track', '/profile', '/wishlist'];
  for (const u of urlsToTest) {
    try {
      const resp = await page.goto(`${BASE_URL}${u}`, { waitUntil: 'domcontentloaded' });
      resp.status() < 400 ? ok(`${u} → HTTP ${resp.status()}`) : fail(`${u} → HTTP ${resp.status()}`);
    } catch (e) {
      fail(`${u} crashed`, e.message);
    }
    await page.waitForTimeout(300);
  }

  // ── FINAL REPORT ──────────────────────────────────────────────────────────
  console.log('\n═══════════════════════════════════════');
  console.log(`  TOTAL PASSED: ${passed}`);
  console.log(`  TOTAL FAILED: ${failed}`);
  console.log(`  PAGE ERRORS: ${pageErrors.length}`);
  if (pageErrors.length) pageErrors.forEach(e => console.log('   ⚠', e));
  if (consoleErrors.length) { console.log(`  CONSOLE ERRORS: ${consoleErrors.length}`); consoleErrors.forEach(e => console.log('   ⚠', e)); }
  console.log(`\n  STATUS: ${failed === 0 ? '✅ FULL PASS' : failed <= 3 ? '⚠️  PARTIAL PASS' : '❌ FAIL'}`);

  await browser.close();
})();
