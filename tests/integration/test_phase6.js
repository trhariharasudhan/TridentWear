const playwright = require('playwright');
(async () => {
  const BASE_URL = process.env.TRIDENT_BASE_URL || 'http://127.0.0.1:8020';
  const browser = await playwright.chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('[console.error] ' + m.text()); });

  // Test 1: Products category chips (only All + T-Shirts should exist)
  await page.goto(`${BASE_URL}/products`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  const chips = await page.evaluate(() => {
    const btns = document.querySelectorAll('[data-main-category]');
    return Array.from(btns).map(b => b.dataset.mainCategory + ':' + b.textContent.trim());
  });
  const productCount = await page.evaluate(() => document.querySelector('[data-product-count]')?.textContent);
  console.log('Category chips:', chips);
  console.log('Product count label:', productCount);
  console.log('Products chips PASS:', chips.every(c => c.startsWith('all') || c.startsWith('tshirt')));

  // Test 2: Search via force-click on wrapper
  await page.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  const searchResult = await page.evaluate(async () => {
    // Open search manually
    const wrapper = document.querySelector('[data-search-wrapper]');
    const icon = wrapper?.querySelector('.search-icon');
    const input = wrapper?.querySelector('[data-search-input]');
    if (!wrapper || !input) return { error: 'No search elements' };
    wrapper.classList.add('is-search-open');
    input.focus();
    input.value = 'black';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 700));
    const drop = document.querySelector('[data-search-results]');
    return {
      wrapperOpen: wrapper.classList.contains('is-search-open'),
      dropdownHidden: drop?.hidden,
      resultItems: drop?.querySelectorAll('.search-result-item').length || 0,
      noResultsMsg: drop?.querySelector('.search-no-results')?.textContent || null,
    };
  });
  console.log('Search result:', searchResult);

  // Test 3: Contact page - no console errors after fix
  await page.goto(`${BASE_URL}/contact`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  const contactState = await page.evaluate(() => ({
    form: !!document.querySelector('[data-contact-form]'),
    nameField: !!document.querySelector('#contact-name'),
    submitBtn: !!document.querySelector('[data-contact-form] button[type=submit]'),
    statusDiv: !!document.querySelector('[data-contact-status]'),
  }));
  console.log('Contact page state:', contactState);

  // Test 4: About page has content
  await page.goto(`${BASE_URL}/about`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);
  const aboutText = await page.evaluate(() => document.querySelector('main')?.innerText?.substring(0, 300));
  console.log('About page content (first 300):', aboutText);

  // Test 5: Mobile OTP login tab switching
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  const loginTabs = await page.evaluate(() => {
    const emailTab = document.getElementById('btn-tab-email');
    const otpTab = document.getElementById('btn-tab-otp');
    const mobileInput = document.getElementById('login-mobile');
    const sendOtpBtn = document.getElementById('send-otp-btn');
    return {
      emailTab: !!emailTab,
      otpTab: !!otpTab,
      mobileInput: !!mobileInput,
      sendOtpBtn: !!sendOtpBtn,
    };
  });
  console.log('Login tabs state:', loginTabs);

  console.log();
  console.log('Page errors:', errors);
  await browser.close();
})();
