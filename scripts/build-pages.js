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

const GITHUB_PAGES_BASE_URL = 'https://trhariharasudhan.github.io/TridentWear';

function slugify(name) {
  if (typeof name !== 'string') return '';
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function escapeHtmlAttr(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function safeJsonLd(obj) {
  return JSON.stringify(obj, null, 2).replace(/</g, '\\u003c');
}

function resolveProductImageUrl(rawImage) {
  let relative = String(rawImage || '').trim();
  if (relative.startsWith('/assets/images/')) {
    relative = relative.slice('/assets/images/'.length);
  } else if (relative.startsWith('assets/images/')) {
    relative = relative.slice('assets/images/'.length);
  } else if (relative.startsWith('/images/')) {
    relative = relative.slice('/images/'.length);
  } else if (relative.startsWith('images/')) {
    relative = relative.slice('images/'.length);
  } else if (relative.startsWith('/')) {
    relative = relative.slice(1);
  }
  return `${GITHUB_PAGES_BASE_URL}/assets/images/${relative}`;
}

function toAbsoluteMetadataImageUrl(rawUrl) {
  if (rawUrl === null || rawUrl === undefined) return rawUrl;
  const trimmed = String(rawUrl).trim();
  if (!trimmed) {
    return rawUrl;
  }

  // Preserve protocol-relative external URLs (e.g. //cdn.example.com/img.jpg)
  if (trimmed.startsWith('//')) {
    return trimmed;
  }

  // Check for URI schemes
  const schemeMatch = trimmed.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/);
  if (schemeMatch) {
    const scheme = schemeMatch[1].toLowerCase();
    // Non-HTTP/HTTPS schemes (data:, javascript:, file:, blob:, ftp:, etc.): leave unchanged
    if (scheme !== 'http' && scheme !== 'https') {
      return rawUrl;
    }

    try {
      const parsed = new URL(trimmed);
      if (parsed.hostname.toLowerCase() === 'trhariharasudhan.github.io') {
        const pathname = parsed.pathname;
        // Already correctly prefixed deployment path
        if (pathname === '/TridentWear' || pathname === '/TridentWear/' || pathname.startsWith('/TridentWear/')) {
          return trimmed;
        }
        // Reject prefix collisions like /TridentWearEvil/...
        if (pathname.startsWith('/TridentWearEvil')) {
          return trimmed;
        }
        // Direct domain assets missing the repository subpath
        if (pathname.startsWith('/assets/')) {
          return `${GITHUB_PAGES_BASE_URL}${pathname}${parsed.search}${parsed.hash}`;
        }
        return trimmed;
      }
      // Legitimate external HTTP/HTTPS URL
      return trimmed;
    } catch {
      return rawUrl;
    }
  }

  // Separate path from query string and hash
  const hashIdx = trimmed.indexOf('#');
  const queryIdx = trimmed.indexOf('?');
  let pathPart = trimmed;
  let suffix = '';

  if (queryIdx !== -1 || hashIdx !== -1) {
    const splitIdx = (queryIdx !== -1 && hashIdx !== -1)
      ? Math.min(queryIdx, hashIdx)
      : (queryIdx !== -1 ? queryIdx : hashIdx);
    pathPart = trimmed.slice(0, splitIdx);
    suffix = trimmed.slice(splitIdx);
  }

  // Handle local path
  if (pathPart === '/TridentWear' || pathPart === '/TridentWear/' || pathPart.startsWith('/TridentWear/')) {
    const sub = pathPart.slice('/TridentWear'.length).replace(/^\/?/, '');
    return `${GITHUB_PAGES_BASE_URL}/${sub}${suffix}`;
  }

  const cleanPath = pathPart.replace(/^\/?/, '');
  return `${GITHUB_PAGES_BASE_URL}/${cleanPath}${suffix}`;
}

function rewriteMetadataImages(content) {
  return content.replace(
    /<meta\s+([^>]*?(?:property=["']og:image(?::(?:url|secure_url))?["']|name=["']twitter:image(?::src)?["'])[^>]*?)>/gi,
    (fullTag) => {
      return fullTag.replace(/\bcontent=(["'])([^"']*?)\1/i, (match, quote, contentVal) => {
        const resolved = toAbsoluteMetadataImageUrl(contentVal);
        return `content=${quote}${resolved}${quote}`;
      });
    }
  );
}

function resolveCanonicalUrl(hrefVal, destRel) {
  if (hrefVal === null || hrefVal === undefined) return hrefVal;
  const raw = String(hrefVal).trim();
  if (!raw) return raw;

  // Preserve protocol-relative external URLs
  if (raw.startsWith('//')) {
    return raw;
  }

  // Check for schemes
  const schemeMatch = raw.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/);
  if (schemeMatch) {
    const scheme = schemeMatch[1].toLowerCase();
    if (scheme !== 'http' && scheme !== 'https') {
      return raw;
    }

    try {
      const parsed = new URL(raw);
      if (parsed.hostname.toLowerCase() !== 'trhariharasudhan.github.io') {
        // Legitimate external canonical URL
        return raw;
      }

      const pathname = parsed.pathname;
      // Reject prefix collisions like /TridentWearEvil
      if (pathname.startsWith('/TridentWearEvil')) {
        return raw;
      }

      if (pathname === '/TridentWear' || pathname === '/TridentWear/' || pathname.startsWith('/TridentWear/')) {
        let cleanRoute = pathname.slice('/TridentWear'.length).replace(/^\//, '').replace(/(?:\.html)?\/?$/, '');
        if (!cleanRoute) {
          return `${GITHUB_PAGES_BASE_URL}/${parsed.search}${parsed.hash}`;
        }
        return `${GITHUB_PAGES_BASE_URL}/${cleanRoute}/${parsed.search}${parsed.hash}`;
      }

      // Root domain without /TridentWear/
      const cleanRoute = pathname.replace(/^\//, '').replace(/(?:\.html)?\/?$/, '');
      const trailing = cleanRoute ? `${cleanRoute}/` : '';
      return `${GITHUB_PAGES_BASE_URL}/${trailing}${parsed.search}${parsed.hash}`;
    } catch {
      return raw;
    }
  }

  // Separate path from query string and hash
  const hashIdx = raw.indexOf('#');
  const queryIdx = raw.indexOf('?');
  let pathPart = raw;
  let suffix = '';

  if (queryIdx !== -1 || hashIdx !== -1) {
    const splitIdx = (queryIdx !== -1 && hashIdx !== -1)
      ? Math.min(queryIdx, hashIdx)
      : (queryIdx !== -1 ? queryIdx : hashIdx);
    pathPart = raw.slice(0, splitIdx);
    suffix = raw.slice(splitIdx);
  }

  // Derive canonical from destRel if provided (directory routes use trailing slash for GitHub Pages)
  if (destRel) {
    if (destRel === 'index.html') {
      return `${GITHUB_PAGES_BASE_URL}/${suffix}`;
    }
    if (destRel.endsWith('/index.html')) {
      const route = destRel.replace(/\/index\.html$/, '');
      return `${GITHUB_PAGES_BASE_URL}/${route}/${suffix}`;
    }
    return `${GITHUB_PAGES_BASE_URL}/${destRel}${suffix}`;
  }

  // Fallback if destRel is not provided
  if (pathPart === '/' || pathPart === '') {
    return `${GITHUB_PAGES_BASE_URL}/${suffix}`;
  }

  if (pathPart === '/TridentWear' || pathPart === '/TridentWear/' || pathPart.startsWith('/TridentWear/')) {
    const cleanRoute = pathPart.slice('/TridentWear'.length).replace(/^\//, '').replace(/(?:\.html)?\/?$/, '');
    if (!cleanRoute) {
      return `${GITHUB_PAGES_BASE_URL}/${suffix}`;
    }
    return `${GITHUB_PAGES_BASE_URL}/${cleanRoute}/${suffix}`;
  }

  const cleanRoute = pathPart.replace(/^\//, '').replace(/(?:\.html)?\/?$/, '');
  return `${GITHUB_PAGES_BASE_URL}/${cleanRoute}/${suffix}`;
}

function rewriteCanonicalLinks(content, destRel) {
  return content.replace(
    /<link\s+([^>]*?rel=["']canonical["'][^>]*?)>/gi,
    (fullTag) => {
      return fullTag.replace(/\bhref=(["'])([^"']*?)\1/i, (match, quote, hrefVal) => {
        const resolved = resolveCanonicalUrl(hrefVal, destRel);
        return `href=${quote}${resolved}${quote}`;
      });
    }
  );
}

function processHtmlForGithubPages(content, destRel = '') {
  // 1. Inject or update <base href="/TridentWear/" />
  if (content.includes('<head>')) {
    if (/<base\s+href="[^"]*"\s*\/?>/.test(content)) {
      content = content.replace(/<base\s+href="[^"]*"\s*\/?>/, '<base href="/TridentWear/" />');
    } else {
      content = content.replace('<head>', '<head>\n    <base href="/TridentWear/" />');
    }
  }

  // 2. Rewrite Open Graph & Twitter metadata images to absolute production URLs
  content = rewriteMetadataImages(content);

  // 3. Rewrite canonical link elements to absolute production URLs before general link rewriting
  content = rewriteCanonicalLinks(content, destRel);

  // 4. Rewrite absolute asset paths
  content = content.replace(/(href|src)="\/(assets\/[^"]*)"/g, '$1="$2"');

  // 5. Rewrite page links to match static pretty URLs
  const routes = [
    'products', 'cart', 'product', 'checkout', 'wishlist', 'login', 'register',
    'profile', 'profile-setup', 'verify', 'about', 'contact', 'admin', 'privacy',
    'terms', 'returns', 'shipping', 'track', 'chat', 'admin/chat', 'faq'
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

function renderStaticProductHtml(template, item, slug) {
  const canonicalUrl = `${GITHUB_PAGES_BASE_URL}/products/${slug}/`;
  const imageUrl = resolveProductImageUrl(item.image);
  const titleText = `${item.name} | TridentWear`;
  const descText = item.description || 'Premium quality product from TridentWear.';

  let html = template;

  // 1. Remove any noindex robots meta tag from the shared template
  html = html.replace(/<meta\s+name=["']robots["'][^>]*>\s*/gi, '');

  // 2. Set document title
  html = html.replace(/<title>[^<]*<\/title>/i, `<title>${escapeHtmlAttr(titleText)}</title>`);

  // 3. Set meta description
  if (/<meta\s+name=["']description["'][^>]*>/i.test(html)) {
    html = html.replace(/<meta\s+name=["']description["'][^>]*>/i, `<meta name="description" content="${escapeHtmlAttr(descText)}"/>`);
  } else {
    html = html.replace('</head>', `    <meta name="description" content="${escapeHtmlAttr(descText)}"/>\n</head>`);
  }

  // 4. Set canonical link
  if (/<link\s+[^>]*?rel=["']canonical["'][^>]*>/i.test(html)) {
    html = html.replace(/<link\s+[^>]*?rel=["']canonical["'][^>]*>/i, `<link rel="canonical" href="${canonicalUrl}" />`);
  } else {
    html = html.replace('</head>', `    <link rel="canonical" href="${canonicalUrl}" />\n</head>`);
  }

  // 5. Open Graph tags
  if (/<meta\s+property=["']og:title["'][^>]*>/i.test(html)) {
    html = html.replace(/<meta\s+property=["']og:title["'][^>]*>/i, `<meta property="og:title" content="${escapeHtmlAttr(titleText)}" />`);
  }
  if (/<meta\s+property=["']og:description["'][^>]*>/i.test(html)) {
    html = html.replace(/<meta\s+property=["']og:description["'][^>]*>/i, `<meta property="og:description" content="${escapeHtmlAttr(descText)}" />`);
  }
  if (/<meta\s+property=["']og:image["'][^>]*>/i.test(html)) {
    html = html.replace(/<meta\s+property=["']og:image["'][^>]*>/i, `<meta property="og:image" content="${imageUrl}" />`);
  }
  if (/<meta\s+property=["']og:url["'][^>]*>/i.test(html)) {
    html = html.replace(/<meta\s+property=["']og:url["'][^>]*>/i, `<meta property="og:url" content="${canonicalUrl}" />`);
  } else {
    html = html.replace('</head>', `    <meta property="og:url" content="${canonicalUrl}" />\n</head>`);
  }
  if (!/<meta\s+property=["']og:type["'][^>]*>/i.test(html)) {
    html = html.replace('</head>', `    <meta property="og:type" content="product" />\n</head>`);
  }

  // 6. Twitter tags
  if (/<meta\s+name=["']twitter:card["'][^>]*>/i.test(html)) {
    html = html.replace(/<meta\s+name=["']twitter:card["'][^>]*>/i, `<meta name="twitter:card" content="summary_large_image" />`);
  } else {
    html = html.replace('</head>', `    <meta name="twitter:card" content="summary_large_image" />\n</head>`);
  }
  if (/<meta\s+name=["']twitter:title["'][^>]*>/i.test(html)) {
    html = html.replace(/<meta\s+name=["']twitter:title["'][^>]*>/i, `<meta name="twitter:title" content="${escapeHtmlAttr(titleText)}" />`);
  } else {
    html = html.replace('</head>', `    <meta name="twitter:title" content="${escapeHtmlAttr(titleText)}" />\n</head>`);
  }
  if (/<meta\s+name=["']twitter:description["'][^>]*>/i.test(html)) {
    html = html.replace(/<meta\s+name=["']twitter:description["'][^>]*>/i, `<meta name="twitter:description" content="${escapeHtmlAttr(descText)}" />`);
  } else {
    html = html.replace('</head>', `    <meta name="twitter:description" content="${escapeHtmlAttr(descText)}" />\n</head>`);
  }
  if (/<meta\s+name=["']twitter:image["'][^>]*>/i.test(html)) {
    html = html.replace(/<meta\s+name=["']twitter:image["'][^>]*>/i, `<meta name="twitter:image" content="${imageUrl}" />`);
  } else {
    html = html.replace('</head>', `    <meta name="twitter:image" content="${imageUrl}" />\n</head>`);
  }

  // 7. JSON-LD Structured Data
  const breadcrumbData = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {
        "@type": "ListItem",
        "position": 1,
        "name": "Home",
        "item": `${GITHUB_PAGES_BASE_URL}/`
      },
      {
        "@type": "ListItem",
        "position": 2,
        "name": "Products",
        "item": `${GITHUB_PAGES_BASE_URL}/products/`
      },
      {
        "@type": "ListItem",
        "position": 3,
        "name": item.name,
        "item": canonicalUrl
      }
    ]
  };

  const productData = {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": item.name,
    "image": [imageUrl],
    "description": descText,
    "sku": `TRI-PROD-${item.id}`,
    "brand": {
      "@type": "Brand",
      "name": "TridentWear"
    },
    "offers": {
      "@type": "Offer",
      "url": canonicalUrl,
      "priceCurrency": "INR",
      "price": item.price,
      "itemCondition": "https://schema.org/NewCondition",
      "availability": (item.stock !== undefined && item.stock !== null && item.stock > 0)
        ? "https://schema.org/InStock"
        : "https://schema.org/OutOfStock"
    }
  };

  const jsonLdBlock = `    <script type="application/ld+json">\n${safeJsonLd(breadcrumbData)}\n    </script>\n    <script type="application/ld+json">\n${safeJsonLd(productData)}\n    </script>\n`;
  html = html.replace('</head>', `${jsonLdBlock}</head>`);

  // 8. Inject data-product-id on <body>
  html = html.replace(/<body([^>]*)>/i, (match, attrs) => {
    if (attrs.includes('data-product-id')) {
      return match.replace(/data-product-id="[^"]*"/, `data-product-id="${item.id}"`);
    }
    return `<body${attrs} data-product-id="${item.id}">`;
  });

  return html;
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

// Pre-build validation: ensure source catalogue exists, is valid, non-empty, and structurally sound
const catalogPath = path.join(srcRoot, 'assets/data/products.json');
if (!fs.existsSync(catalogPath)) {
  throw new Error(`[FATAL BUILD ERROR] Catalogue source missing: ${catalogPath}`);
}
let catalogData;
try {
  catalogData = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
} catch (e) {
  throw new Error(`[FATAL BUILD ERROR] Catalogue JSON parse failed: ${e.message}`);
}
if (!Array.isArray(catalogData) || catalogData.length === 0) {
  throw new Error(`[FATAL BUILD ERROR] Refusing build: catalogue is empty or not an array (${Array.isArray(catalogData) ? '0 items' : typeof catalogData})`);
}
const seenIds = new Set();
const seenSlugs = new Map();
const imagesDir = path.resolve(srcRoot, 'assets/images');
for (let i = 0; i < catalogData.length; i++) {
  const item = catalogData[i];
  if (!item || typeof item !== 'object' || Array.isArray(item)) {
    throw new Error(`[FATAL BUILD ERROR] Item at index ${i} is not a valid non-null object.`);
  }

  // 1. Validate ID: positive integer and globally unique
  if (typeof item.id !== 'number' || !Number.isInteger(item.id) || item.id <= 0) {
    throw new Error(`[FATAL BUILD ERROR] Item at index ${i} has invalid ID: ${item.id} (must be a positive integer)`);
  }
  if (seenIds.has(item.id)) {
    throw new Error(`[FATAL BUILD ERROR] Duplicate product ID detected: ${item.id} at index ${i}`);
  }
  seenIds.add(item.id);

  // 2. Validate Name: non-empty string after trimming
  if (typeof item.name !== 'string' || item.name.trim().length === 0) {
    throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) has invalid name: ${JSON.stringify(item.name)} (must be a non-empty string)`);
  }

  // 3. Validate Category: non-empty string after trimming
  if (typeof item.category !== 'string' || item.category.trim().length === 0) {
    throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) has invalid category: ${JSON.stringify(item.category)} (must be a non-empty string)`);
  }

  // 4. Validate Price: finite positive number
  if (typeof item.price !== 'number' || !Number.isFinite(item.price) || item.price <= 0) {
    throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) has invalid price: ${item.price} (must be a finite positive number)`);
  }

  // 5. Validate Image: non-empty string after trimming
  if (typeof item.image !== 'string' || item.image.trim().length === 0) {
    throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) has invalid image: ${JSON.stringify(item.image)} (must be a non-empty string)`);
  }

  // 6. Validate Image Path Resolution: external HTTP/HTTPS URL or local file under assets/images without traversal
  const trimmedImage = item.image.trim();
  const hasScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(trimmedImage);
  if (hasScheme || trimmedImage.startsWith('//') || trimmedImage.startsWith('http//') || trimmedImage.startsWith('https//')) {
    let parsedUrl;
    try {
      parsedUrl = new URL(trimmedImage);
    } catch (err) {
      throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) has malformed image URL: ${item.image} (${err.message})`);
    }
    if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
      throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) has unsupported image URL scheme: ${parsedUrl.protocol} (only http: and https: are allowed)`);
    }
    if (!parsedUrl.hostname || parsedUrl.hostname.trim().length === 0) {
      throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) has invalid image URL hostname: ${item.image}`);
    }
  } else {
    let relativeImagePath = trimmedImage;
    if (relativeImagePath.startsWith('/assets/images/')) {
      relativeImagePath = relativeImagePath.slice('/assets/images/'.length);
    } else if (relativeImagePath.startsWith('assets/images/')) {
      relativeImagePath = relativeImagePath.slice('assets/images/'.length);
    } else if (relativeImagePath.startsWith('/images/')) {
      relativeImagePath = relativeImagePath.slice('/images/'.length);
    } else if (relativeImagePath.startsWith('images/')) {
      relativeImagePath = relativeImagePath.slice('images/'.length);
    } else if (relativeImagePath.startsWith('/')) {
      relativeImagePath = relativeImagePath.slice(1);
    }

    if (relativeImagePath.trim().length === 0) {
      throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) has empty image subpath after prefix removal: ${item.image}`);
    }

    const resolvedImgPath = path.resolve(imagesDir, relativeImagePath);
    if (!resolvedImgPath.startsWith(imagesDir + path.sep)) {
      throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) image path attempts traversal or resolves outside assets/images: ${item.image} (resolved to: ${resolvedImgPath})`);
    }
    if (!fs.existsSync(resolvedImgPath)) {
      throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) references missing local image file: ${item.image} (resolved to: ${resolvedImgPath})`);
    }
    const stat = fs.statSync(resolvedImgPath);
    if (!stat.isFile()) {
      throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) image path is not a regular file: ${item.image} (resolved to: ${resolvedImgPath})`);
    }
  }

  // 7. Validate Stock: non-negative integer when present
  if (item.stock !== undefined && item.stock !== null) {
    if (typeof item.stock !== 'number' || !Number.isInteger(item.stock) || item.stock < 0) {
      throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) has invalid stock: ${item.stock} (must be an integer >= 0)`);
    }
  }

  // 8. Validate Slug: lowercase alphanumeric and hyphens, non-empty, unique
  const slug = slugify(item.name);
  if (!slug) {
    throw new Error(`[FATAL BUILD ERROR] Item at index ${i} (id: ${item.id}) generated an empty slug from name: ${JSON.stringify(item.name)}`);
  }
  if (seenSlugs.has(slug)) {
    throw new Error(`[FATAL BUILD ERROR] Slug collision detected: "${slug}" generated for id ${item.id} already used by id ${seenSlugs.get(slug)}`);
  }
  seenSlugs.set(slug, item.id);
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

// Copy static robots.txt
const robotsSrc = path.join(srcRoot, 'robots.txt');
const robotsDest = path.join(outRoot, 'robots.txt');
if (fs.existsSync(robotsSrc)) {
  fs.copyFileSync(robotsSrc, robotsDest);
}

// Generate authoritative sitemap: source sitemap (10 fixed pages) + 24 catalogue product URLs
const sitemapSrc = path.join(srcRoot, 'sitemap.xml');
const sitemapDest = path.join(outRoot, 'sitemap.xml');
if (!fs.existsSync(sitemapSrc)) {
  throw new Error(`[FATAL BUILD ERROR] Source sitemap missing: ${sitemapSrc}`);
}
const sourceSitemapContent = fs.readFileSync(sitemapSrc, 'utf8');

const sitemapLocSet = new Set();
const locRegex = /<loc>([^<]+)<\/loc>/g;
let locMatch;
while ((locMatch = locRegex.exec(sourceSitemapContent)) !== null) {
  sitemapLocSet.add(locMatch[1]);
}
if (sitemapLocSet.size !== 10) {
  throw new Error(`[FATAL BUILD ERROR] Expected exactly 10 fixed URLs in source sitemap, found ${sitemapLocSet.size}`);
}

let productSitemapEntries = '';
for (const item of catalogData) {
  const slug = slugify(item.name);
  const prodUrl = `${GITHUB_PAGES_BASE_URL}/products/${slug}/`;
  if (sitemapLocSet.has(prodUrl)) {
    throw new Error(`[FATAL BUILD ERROR] Product URL collision in sitemap: ${prodUrl}`);
  }
  sitemapLocSet.add(prodUrl);
  productSitemapEntries += `  <url>\n    <loc>${prodUrl}</loc>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n`;
}

if (sitemapLocSet.size !== 34) {
  throw new Error(`[FATAL BUILD ERROR] Expected exactly 34 URLs in generated sitemap, got ${sitemapLocSet.size}`);
}

if (!sourceSitemapContent.includes('</urlset>')) {
  throw new Error('[FATAL BUILD ERROR] Malformed source sitemap: missing </urlset>');
}

const finalSitemapContent = sourceSitemapContent.replace('</urlset>', `${productSitemapEntries}</urlset>`);
fs.writeFileSync(sitemapDest, finalSitemapContent, 'utf8');

// Process and map standard HTML files
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
  'pages/info/faq.html': 'faq/index.html',
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
    processed = processHtmlForGithubPages(processed, destRel);
    fs.writeFileSync(destPath, processed, 'utf8');
  }
}

// Process and generate 24 static product pages at dist/products/{slug}/index.html
const productTemplatePath = path.join(srcRoot, 'pages/shop/product.html');
if (!fs.existsSync(productTemplatePath)) {
  throw new Error(`[FATAL BUILD ERROR] Product template missing: ${productTemplatePath}`);
}
const rawProductTemplate = fs.readFileSync(productTemplatePath, 'utf8');

for (const item of catalogData) {
  const slug = slugify(item.name);
  const destRel = `products/${slug}/index.html`;
  const destPath = path.join(outRoot, destRel);
  ensureDir(path.dirname(destPath));

  let html = renderStaticProductHtml(rawProductTemplate, item, slug);
  html = processContent(html);
  html = processHtmlForGithubPages(html, destRel);
  fs.writeFileSync(destPath, html, 'utf8');
}

// Ensure .nojekyll exists in dist
fs.writeFileSync(path.join(outRoot, '.nojekyll'), '', 'utf8');

console.log('Build completed');
