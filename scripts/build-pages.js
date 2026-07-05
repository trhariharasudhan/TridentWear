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

function copyAndProcess(src, dest) {
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    ensureDir(dest);
    const entries = fs.readdirSync(src);
    for (const entry of entries) {

    // Skip generated output folder
    if (entry === 'dist') {
      continue;
    }

    copyAndProcess(
      path.join(src, entry),
      path.join(dest, entry)
    );
  }
  } else if (stat.isFile()) {
    ensureDir(path.dirname(dest));
    if (src.endsWith('.html')) {
      const raw = fs.readFileSync(src, 'utf8');
      const processed = processContent(raw);
      fs.writeFileSync(dest, processed, 'utf8');
    } else {
      // binary or other assets, just copy
      fs.copyFileSync(src, dest);
    }
  }
}

// Clean output folder
if (fs.existsSync(outRoot)) {
  fs.rmdirSync(outRoot, { recursive: true });
}
ensureDir(outRoot);

copyAndProcess(srcRoot, outRoot);

// Ensure .nojekyll exists in dist
fs.writeFileSync(path.join(outRoot, '.nojekyll'), '', 'utf8');

console.log('Build completed');
