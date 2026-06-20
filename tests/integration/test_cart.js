const playwright = require('playwright');
(async () => {
  const BASE_URL = process.env.TRIDENT_BASE_URL || 'http://127.0.0.1:8020';
  const browser = await playwright.chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  
  await page.goto(`${BASE_URL}/product?id=1`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  
  // Select size
  const sizeBtn = await page.$('#detail-sizes button');
  if (sizeBtn) {
    await sizeBtn.click();
    await page.waitForTimeout(300);
  }
  
  // Add to cart
  const atcBtn = await page.$('#detail-add-cart');
  if (atcBtn) {
    await atcBtn.click();
    await page.waitForTimeout(2000);
  }
  
  const drawerState = await page.evaluate(() => {
    const drawer = document.querySelector('[data-cart-drawer]');
    if (!drawer) return { exists: false };
    const style = window.getComputedStyle(drawer);
    const panel = drawer.querySelector('.cart-drawer-panel');
    const list = drawer.querySelector('[data-cart-drawer-list]');
    const panelStyle = panel ? window.getComputedStyle(panel) : null;
    return {
      exists: true,
      isOpen: drawer.classList.contains('is-open'),
      drawerDisplay: style.display,
      panelTransform: panelStyle ? panelStyle.transform : 'no panel',
      panelColor: panelStyle ? panelStyle.color : 'no panel',
      panelBg: panelStyle ? panelStyle.backgroundColor : 'no panel',
      listHTML: list ? list.innerHTML.substring(0, 500) : 'NO LIST',
      cartBadge: (document.querySelector('[data-cart-count]') || {}).textContent || 'none',
      localStorageCart: localStorage.getItem('tw_cart') || 'empty',
    };
  });
  
  console.log('Drawer State:', JSON.stringify(drawerState, null, 2));
  console.log('Page Errors:', errors);
  
  await browser.close();
})();
