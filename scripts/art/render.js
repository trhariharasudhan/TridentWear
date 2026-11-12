// Rasterise generated garment SVGs to transparent WebP using headless Chrome.
// Usage: node scripts/art/render.js   (needs: npm i, and Chrome or `npx playwright install chromium`)
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const OUT_SVG = path.join(__dirname, 'out');
const DEST = path.resolve(__dirname, '../../frontend/assets/images/products');

(async () => {
  fs.mkdirSync(DEST, { recursive: true });
  const jobs = JSON.parse(fs.readFileSync(path.join(OUT_SVG, 'jobs.json'), 'utf8'));
  const exe = process.env.CHROME_PATH || undefined;
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const page = await browser.newPage({ viewport: { width: 1000, height: 1200 } });
  for (const name of jobs) {
    const svg = fs.readFileSync(path.join(OUT_SVG, `${name}.svg`), 'utf8');
    await page.setContent(`<html><head><style>html,body{margin:0;background:transparent}</style>
      <link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800;900&display=swap" rel="stylesheet"></head>
      <body>${svg}</body></html>`, { waitUntil: 'networkidle' }).catch(() => {});
    const dataUrl = await page.evaluate(async () => {
      await document.fonts.ready;
      const svgEl = document.querySelector('svg');
      const c = document.createElement('canvas');
      c.width = 900; c.height = 1080;
      const img = new Image();
      const xml = new XMLSerializer().serializeToString(svgEl);
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
      await img.decode();
      c.getContext('2d').drawImage(img, 0, 0, 900, 1080);
      return c.toDataURL('image/webp', 0.9);
    });
    fs.writeFileSync(path.join(DEST, `${name}.webp`), Buffer.from(dataUrl.split(',')[1], 'base64'));
    process.stdout.write('.');
  }
  await browser.close();
  console.log(`\nrendered ${jobs.length} images -> ${DEST}`);
})();
