// AI Fit Check page: live camera or uploaded photo + garment overlay.
import { mountChrome, $, $$, esc, icon, inr, img, toast, busy, params, logoSvg } from '../ui.js';
import { getProducts, cart } from '../store.js';
import { api } from '../api.js';
import { PoseEngine, Smoother, bodyTargets, drawGarment, drawGarmentLive, ClothSim, fitMapper } from '../tryon-engine.js';

await mountChrome({ page: 'tryon' });

const SIZES = ['S', 'M', 'L', 'XL', 'XXL'];
const SCALE = [0.93, 1, 1.07, 1.14, 1.21];
const el = {
  viewport: $('[data-viewport]'), video: $('[data-video]'), canvas: $('[data-canvas]'),
  intro: $('[data-intro]'), controls: $('[data-controls]'), status: $('[data-status]'),
  note: $('[data-engine-note]'), hudProduct: $('[data-hud-product]'),
};
const ctx = el.canvas.getContext('2d');
const state = {
  product: null, garment: null, source: null /* 'camera' | 'photo' */, photo: null, photoBlob: null,
  photoLandmarks: null, facing: 'user', mirror: true, sizeIdx: 1, offsetY: 0, drag: { x: 0, y: 0 },
  showPoints: false, running: false, engine: null, engineError: null, stream: null, lastPose: null,
};
const smoother = new Smoother(0.5);
const cloth = new ClothSim(); // hem inertia for Live+

$('[data-flip]').innerHTML = icon.flip;
$('[data-stop]').innerHTML = icon.close;

// ---------------------------------------------------------------- products
const products = (await getProducts()).filter((p) => p.stock > 0 || true);
const wanted = Number(params().get('id'));
$('[data-picker]').innerHTML = products.map((p) => `<button data-pick="${p.id}" title="${esc(p.name)} — ${esc(p.base_color)}"><img src="${img(p.image)}" alt="${esc(p.name)} ${esc(p.base_color)}" loading="lazy"></button>`).join('');
$$('[data-pick]').forEach((b) => {
  b.addEventListener('click', () => selectProduct(Number(b.dataset.pick)));
  // Drag a piece onto yourself (desktop): drop it on the camera view to try it on
  b.draggable = true;
  b.addEventListener('dragstart', (e) => { e.dataTransfer.setData('text/tw-product', b.dataset.pick); e.dataTransfer.effectAllowed = 'copy'; el.viewport.classList.add('is-drop'); });
  b.addEventListener('dragend', () => el.viewport.classList.remove('is-drop', 'is-over'));
});
el.viewport.addEventListener('dragover', (e) => { if (e.dataTransfer.types.includes('text/tw-product')) { e.preventDefault(); el.viewport.classList.add('is-over'); } });
el.viewport.addEventListener('dragleave', () => el.viewport.classList.remove('is-over'));
el.viewport.addEventListener('drop', (e) => {
  const id = Number(e.dataTransfer.getData('text/tw-product')); if (!id) return;
  e.preventDefault(); el.viewport.classList.remove('is-drop', 'is-over'); selectProduct(id);
});

function loadImage(src) {
  return new Promise((res, rej) => { const i = new Image(); i.crossOrigin = 'anonymous'; i.onload = () => res(i); i.onerror = rej; i.src = src; });
}
async function selectProduct(id) {
  const p = products.find((x) => x.id === id) || products[0];
  state.product = p;
  $$('[data-pick]').forEach((b) => b.classList.toggle('is-on', Number(b.dataset.pick) === p.id));
  el.hudProduct.textContent = `${p.name} · ${p.base_color}`;
  state.garment = await loadImage(img(p.image));
  history.replaceState(null, '', `?id=${p.id}`);
  $('[data-product-panel]').innerHTML = `
    <div style="display:flex;gap:12px;align-items:center"><img src="${img(p.image)}" alt="" style="width:64px;height:76px;object-fit:contain;background:var(--studio-1);border-radius:10px">
      <div><b>${esc(p.name)}</b><div class="muted" style="font-size:13px">${esc(p.base_color)} · ${inr(p.price)}</div><a class="linkish" href="product.html?id=${p.id}">View details</a></div></div>
    <button class="btn btn--block" data-add>Add size ${SIZES[state.sizeIdx]} to bag</button>`;
  $('[data-add]').addEventListener('click', () => {
    cart.add(p.id, SIZES[state.sizeIdx], 1);
    toast(`Added ${p.name} (${SIZES[state.sizeIdx]})`, { image: img(p.image), link: { href: 'cart.html', label: 'View bag' } });
  });
  if (state.source === 'photo') renderPhoto();
}
await selectProduct(wanted || products.find((p) => p.featured)?.id || products[0]?.id);

// ---------------------------------------------------------------- controls
const fit = $('[data-fit]');
fit.addEventListener('input', () => {
  state.sizeIdx = Number(fit.value);
  $('[data-fit-label]').textContent = SIZES[state.sizeIdx];
  const add = $('[data-add]'); if (add) add.textContent = `Add size ${SIZES[state.sizeIdx]} to bag`;
  if (state.source === 'photo') renderPhoto();
});
$('[data-offset]').addEventListener('input', (e) => { state.offsetY = Number(e.target.value); if (state.source === 'photo') renderPhoto(); });
$('[data-mirror]').addEventListener('change', (e) => { state.mirror = e.target.checked; if (state.source === 'photo') renderPhoto(); });
$('[data-landmarks]').addEventListener('change', (e) => { state.showPoints = e.target.checked; if (state.source === 'photo') renderPhoto(); });

// drag to nudge the garment
let dragStart = null;
el.canvas.addEventListener('pointerdown', (e) => { dragStart = { x: e.clientX, y: e.clientY, ox: state.drag.x, oy: state.drag.y }; el.canvas.setPointerCapture(e.pointerId); });
el.canvas.addEventListener('pointermove', (e) => {
  if (!dragStart) return;
  const k = el.canvas.width / el.canvas.clientWidth;
  state.drag = { x: dragStart.ox + (e.clientX - dragStart.x) * k, y: dragStart.oy + (e.clientY - dragStart.y) * k };
  if (state.source === 'photo') renderPhoto();
});
el.canvas.addEventListener('pointerup', () => (dragStart = null));
el.canvas.style.touchAction = 'none';

function setStatus(text, live = false) {
  el.status.classList.toggle('is-live', live);
  el.status.querySelector('span').textContent = text;
}
function sizeCanvas() {
  const r = el.viewport.getBoundingClientRect();
  const dpr = Math.min(2, devicePixelRatio || 1);
  el.canvas.width = Math.round(r.width * dpr);
  el.canvas.height = Math.round(r.height * dpr);
}
addEventListener('resize', () => { sizeCanvas(); if (state.source === 'photo') renderPhoto(); });
sizeCanvas();

// ---------------------------------------------------------------- engine
const enginePromise = new PoseEngine().init()
  .then((e) => { state.engine = e; el.note.textContent = 'Pose engine ready · runs on your device'; return e; })
  .catch((err) => {
    state.engineError = err;
    el.note.textContent = "Couldn't load the AI pose engine (offline or blocked). Manual mode: drag the garment to place it.";
    console.warn('[tryon] pose engine failed', err);
    return null;
  });

api.tryonStatus().then((s) => { if (s?.ai_enabled) $('[data-ai-panel]').hidden = false; }).catch(() => {});

// ---------------------------------------------------------------- shared render
function paint(source, srcW, srcH, landmarks, fitMode) {
  const cw = el.canvas.width, ch = el.canvas.height;
  const mirror = state.mirror;
  const map = fitMapper(srcW, srcH, cw, ch, { mode: fitMode, mirror });
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = '#0b0c11'; ctx.fillRect(0, 0, cw, ch);
  ctx.save();
  if (mirror) { ctx.translate(cw, 0); ctx.scale(-1, 1); }
  ctx.drawImage(source, ...map.rect);
  ctx.restore();

  const k = ch / 900;
  let targets = bodyTargets(landmarks, map.toCanvas, {
    scale: SCALE[state.sizeIdx], offsetX: state.drag.x, offsetY: state.drag.y + state.offsetY * 6 * k,
  });
  if (!targets && (state.engineError || state.source === 'photo')) {
    // manual placement fallback: centred torso box
    const span = Math.min(cw, ch * 0.75) * 0.27 * SCALE[state.sizeIdx];
    const cx = cw / 2 + state.drag.x, top = ch * 0.3 + state.drag.y + state.offsetY * 6 * k;
    targets = { ls: [cx + span / 2, top], rs: [cx - span / 2, top], hip: [cx, top + span * 1.45], quality: 'manual' };
  }
  if (targets && state.garment) {
    if (mirror && targets.quality === 'manual') [targets.ls, targets.rs] = [targets.rs, targets.ls];
    // Live+ (mesh that follows the body, sleeves, cloth sway, light match) when a body is tracked;
    // the flat 3-point fit for manual placement.
    if (targets.quality !== 'manual') {
      drawGarmentLive(ctx, state.garment, state.product?.tryon, targets, { sim: cloth, light: { source, rect: map.rect, mirror } });
    } else {
      drawGarment(ctx, state.garment, state.product?.tryon, targets);
    }
  }
  if (state.showPoints && landmarks) {
    ctx.fillStyle = '#ffc448';
    for (const i of [11, 12, 13, 14, 23, 24]) {
      const lm = landmarks[i]; if (!lm) continue;
      const [x, y] = map.toCanvas(lm.x, lm.y);
      ctx.beginPath(); ctx.arc(x, y, 6 * Math.max(1, k), 0, Math.PI * 2); ctx.fill();
    }
  }
  return targets;
}

// ---------------------------------------------------------------- camera mode
async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) { toast('Camera not supported in this browser. Try uploading a photo.', { type: 'error' }); return; }
  if (!isSecureContext) { toast('Camera needs HTTPS (or localhost).', { type: 'error' }); return; }
  stopCamera();
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: state.facing, width: { ideal: 1280 }, height: { ideal: 960 } } });
  } catch (err) {
    const msg = err.name === 'NotAllowedError' ? 'Camera permission was denied. Allow it in your browser settings, or upload a photo instead.' : `Couldn't open the camera (${err.name}).`;
    toast(msg, { type: 'error', timeout: 6000 }); return;
  }
  el.video.srcObject = state.stream;
  await el.video.play();
  state.source = 'camera'; state.drag = { x: 0, y: 0 };
  el.intro.hidden = true; el.controls.hidden = false;
  $('[data-mirror]').checked = state.mirror = state.facing === 'user';
  setStatus(state.engine ? 'Live · tracking' : 'Live · loading AI…', true);
  await enginePromise;
  if (state.engine) await state.engine.setMode('VIDEO');
  state.running = true;
  loop();
}
function stopCamera() {
  state.running = false;
  state.stream?.getTracks().forEach((t) => t.stop());
  state.stream = null;
}
let lostFrames = 0;
function loop() {
  if (!state.running || state.source !== 'camera') return;
  const v = el.video;
  if (v.readyState >= 2) {
    const raw = state.engine ? state.engine.detectVideo(v) : null;
    const lm = smoother.push(raw);
    const t = paint(v, v.videoWidth, v.videoHeight, lm, 'cover');
    if (state.engine) {
      lostFrames = t ? 0 : lostFrames + 1;
      if (lostFrames > 20) setStatus('Step back — show shoulders', true);
      else if (t) setStatus(t.quality === 'full' ? 'Live · full body' : 'Live · upper body', true);
    }
  }
  requestAnimationFrame(loop);
}
document.addEventListener('visibilitychange', () => { if (document.hidden && state.source === 'camera') { state.running = false; } else if (!document.hidden && state.stream && state.source === 'camera' && !state.running) { state.running = true; loop(); } });

$('[data-start]').addEventListener('click', startCamera);
$('[data-flip]').addEventListener('click', () => { state.facing = state.facing === 'user' ? 'environment' : 'user'; startCamera(); });
$('[data-stop]').addEventListener('click', () => {
  stopCamera(); state.source = null; el.intro.hidden = false; el.controls.hidden = true; setStatus('Camera off');
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, el.canvas.width, el.canvas.height);
});

// ---------------------------------------------------------------- photo mode
$('[data-upload]').addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith('image/')) { toast('Please choose an image file.', { type: 'error' }); return; }
  stopCamera();
  state.photoBlob = file;
  const url = URL.createObjectURL(file);
  state.photo = await loadImage(url);
  state.source = 'photo'; state.drag = { x: 0, y: 0 };
  state.mirror = false; $('[data-mirror]').checked = false;
  el.intro.hidden = true; el.controls.hidden = false; $('[data-flip]').hidden = true;
  setStatus('Analysing photo…');
  renderPhoto();
  await enginePromise;
  if (state.engine) {
    try { state.photoLandmarks = await state.engine.detectImage(state.photo); } catch { state.photoLandmarks = null; }
    setStatus(state.photoLandmarks ? 'Photo · body found' : 'No body found — drag to place', !!state.photoLandmarks);
  } else setStatus('Manual mode — drag to place');
  renderPhoto();
});
function renderPhoto() {
  if (state.source !== 'photo' || !state.photo) return;
  paint(state.photo, state.photo.naturalWidth, state.photo.naturalHeight, state.photoLandmarks, 'contain');
}

// ---------------------------------------------------------------- snapshot
$('[data-snap]').addEventListener('click', async () => {
  const flash = $('[data-flash]'); flash.classList.remove('is-on'); void flash.offsetWidth; flash.classList.add('is-on');
  const out = document.createElement('canvas');
  out.width = el.canvas.width; out.height = el.canvas.height;
  const o = out.getContext('2d');
  o.drawImage(el.canvas, 0, 0);
  // branded footer strip
  const h = Math.round(out.height * 0.075);
  o.fillStyle = 'rgba(18,20,29,.82)'; o.fillRect(0, out.height - h, out.width, h);
  o.fillStyle = '#d4b06a'; o.font = `760 ${Math.round(h * 0.4)}px 'Bricolage Grotesque', sans-serif`; o.textBaseline = 'middle';
  o.fillText('TridentWear · Fit Check', h * 0.5, out.height - h / 2);
  o.fillStyle = '#fff'; o.textAlign = 'right'; o.font = `500 ${Math.round(h * 0.3)}px 'Bricolage Grotesque', sans-serif`;
  o.fillText(`${state.product.name} · ${SIZES[state.sizeIdx]}`, out.width - h * 0.5, out.height - h / 2);
  const blob = await new Promise((r) => out.toBlob(r, 'image/jpeg', 0.9));
  const url = URL.createObjectURL(blob);
  const card = document.createElement('div');
  card.className = 'shot';
  card.innerHTML = `<img src="${url}" alt="Your fit check"><div style="display:flex;gap:6px;padding:10px">
    <a class="btn btn--sm" style="flex:1" href="${url}" download="tridentwear-fit-check.jpg">${icon.download}</a>
    <button class="btn btn--ghost btn--sm" style="flex:1" data-share>${icon.share}</button></div>`;
  $('[data-shots]').prepend(card);
  $('[data-share]', card).addEventListener('click', async () => {
    const f = new File([blob], 'tridentwear-fit-check.jpg', { type: 'image/jpeg' });
    if (navigator.canShare?.({ files: [f] })) { try { await navigator.share({ files: [f], title: 'My TridentWear fit check' }); } catch {} }
    else toast('Sharing not supported here — use download instead.');
  });
  saveLook(out, state.product, SIZES[state.sizeIdx]);
  toast('Fit check saved below and in your account', { link: { href: 'account.html#looks', label: 'View' } });
});

// ---------------------------------------------------------------- optional HD AI render (server)
$('[data-ai-render]').addEventListener('click', async (e) => {
  if (!state.photoBlob) { toast('Upload a full-length photo first, then generate.', { type: 'error' }); return; }
  const fd = new FormData();
  fd.append('product_id', state.product.id);
  fd.append('photo', state.photoBlob, state.photoBlob.name || 'photo.jpg');
  busy(e.currentTarget, true, 'Rendering… ~30s');
  try {
    const r = await api.tryonGenerate(fd);
    const card = document.createElement('div');
    card.className = 'shot';
    card.innerHTML = `<img src="${esc(r.image_url)}" alt="AI try-on render"><div style="padding:10px"><a class="btn btn--sm btn--block" href="${esc(r.image_url)}" target="_blank" rel="noopener">${icon.download} Open HD render</a></div>`;
    $('[data-shots]').prepend(card);
  } catch (ex) { toast(ex.status === 401 ? 'Please sign in to use HD renders.' : ex.message, { type: 'error', timeout: 6000 }); }
  finally { busy(e.currentTarget, false); }
});

// Keep the last 6 fit checks on this device (small JPEGs) so they show up under Account > My fit checks.
function saveLook(canvas, product, size) {
  try {
    const w = 360, h = Math.round((canvas.height / canvas.width) * w);
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    c.getContext('2d').drawImage(canvas, 0, 0, w, h);
    const looks = JSON.parse(localStorage.getItem('tw_looks') || '[]');
    looks.unshift({ src: c.toDataURL('image/jpeg', 0.78), id: product.id, name: product.name, size, at: Date.now() });
    localStorage.setItem('tw_looks', JSON.stringify(looks.slice(0, 6)));
  } catch { /* storage full or blocked: the on-page copy still works */ }
}

addEventListener('pagehide', stopCamera);
await logoSvg();
