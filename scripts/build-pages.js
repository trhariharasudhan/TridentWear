const fs = require('fs');
const path = require('path');

const srcRoot = path.resolve(__dirname, '../frontend');
const outRoot = path.resolve(__dirname, '../frontend/dist');

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function loadComponent(name) {
  const compPath = path.join(srcRoot, 'components', `${name}.html`);
  return fs.readFileSync(compPath, 'utf8');
}

function processContent(content) {
  return content.replace(/\{\{\s*component:([a-zA-Z0-9_-]+)\s*\}\}/g, (_, name) => {
    const comp = loadComponent(name.trim());
    return comp || '';
  });
}

function processHtmlForGithubPages(content) {
  // 1. Inject or update <base href="/TridentWear/" />
  if (content.includes('<head>')) {
    if (/<base\s+href="[^"]*"\s*\/?>/.test(content)) {
      content = content.replace(/<base\s+href="[^"]*"\s*\/?>/, '<base href="/TridentWear/" />');
    } else {
      content = content.replace('<head>', '<head>\n    <base href="/TridentWear/" />');
    }
  }

  // 2. Rewrite absolute asset paths
  content = content.replace(/(href|src)="\/(assets\/[^"]*)"/g, '$1="$2"');

  // 3. Rewrite page links to match static pretty URLs
  const routes = [
    'products', 'cart', 'product', 'checkout', 'wishlist', 'login', 'register',
    'profile', 'profile-setup', 'verify', 'about', 'contact', 'admin', 'privacy',
    'terms', 'returns', 'shipping', 'track', 'chat', 'admin/chat'
  ];

  // Replace href="/" with href="" so it goes to base href
  content = content.replace(/href="\/"/g, 'href=""');

  // For each route, replace href="/route" or href="/route/" or href="/route.html" with href="route/"
  const sortedRoutes = [...routes].sort((a, b) => b.length - a.length);
  for (const r of sortedRoutes) {
    const regex = new RegExp('href="/' + r + '(?:\\.html)?/?(\\?[^"]*|#[^"]*)?"', 'g');
    content = content.replace(regex, 'href="' + r + '/$1"');
  }

  return content;
}

// Helper to copy directory recursively
function copyDir(src, dest) {
  ensureDir(dest);
  const entries = fs.readdirSync(src);
  for (const entry of entries) {
    const srcPath = path.join(src, entry);
    const destPath = path.join(dest, entry);
    const stat = fs.statSync(srcPath);
    if (stat.isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

// Clean output folder
if (fs.existsSync(outRoot)) {
  if (fs.rmSync) {
    fs.rmSync(outRoot, { recursive: true, force: true });
  } else {
    fs.rmdirSync(outRoot, { recursive: true });
  }
}
ensureDir(outRoot);

// Copy assets folder
const assetsSrc = path.join(srcRoot, 'assets');
const assetsDest = path.join(outRoot, 'assets');
if (fs.existsSync(assetsSrc)) {
  copyDir(assetsSrc, assetsDest);
}

// Copy static text/xml files if they exist
const filesToCopy = ['robots.txt', 'sitemap.xml'];
for (const file of filesToCopy) {
  const srcFile = path.join(srcRoot, file);
  const destFile = path.join(outRoot, file);
  if (fs.existsSync(srcFile)) {
    fs.copyFileSync(srcFile, destFile);
  }
}

// Process and map HTML files
const htmlMappings = {
  'index.html': 'index.html',
  'pages/shop/products.html': 'products/index.html',
  'pages/shop/cart.html': 'cart/index.html',
  'pages/shop/product.html': 'product/index.html',
  'pages/shop/checkout.html': 'checkout/index.html',
  'pages/shop/wishlist.html': 'wishlist/index.html',
  'pages/account/login.html': 'login/index.html',
  'pages/account/register.html': 'register/index.html',
  'pages/account/profile.html': 'profile/index.html',
  'pages/account/profile-setup.html': 'profile-setup/index.html',
  'pages/account/verify.html': 'verify/index.html',
  'pages/info/about.html': 'about/index.html',
  'pages/info/contact.html': 'contact/index.html',
  'pages/admin/admin.html': 'admin/index.html',
  'pages/admin/chat.html': 'admin/chat/index.html',
  'pages/support/chat.html': 'chat/index.html',
  'pages/support/track.html': 'track/index.html',
  'pages/legal/privacy.html': 'privacy/index.html',
  'pages/legal/terms.html': 'terms/index.html',
  'pages/legal/returns.html': 'returns/index.html',
  'pages/legal/shipping.html': 'shipping/index.html',
  'pages/error/404.html': '404.html',
};

for (const [srcRel, destRel] of Object.entries(htmlMappings)) {
  const srcPath = path.join(srcRoot, srcRel);
  const destPath = path.join(outRoot, destRel);
  if (fs.existsSync(srcPath)) {
    ensureDir(path.dirname(destPath));
    const raw = fs.readFileSync(srcPath, 'utf8');
    let processed = processContent(raw);
    processed = processHtmlForGithubPages(processed);
    fs.writeFileSync(destPath, processed, 'utf8');
  }
}

// Ensure .nojekyll exists in dist
fs.writeFileSync(path.join(outRoot, '.nojekyll'), '', 'utf8');

console.log('Build completed');
