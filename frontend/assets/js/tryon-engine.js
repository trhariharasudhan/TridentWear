// AI Fit Check engine — pose tracking + garment warping, 100% in the browser.
//
// 1. MediaPipe Pose Landmarker (WASM/GPU, loaded from CDN) finds 33 body
//    landmarks per frame. We use shoulders (11, 12) and hips (23, 24).
// 2. Each product image carries "tryon" anchors: where its shoulders and hem
//    centre sit inside the PNG (normalised 0..1).
// 3. A 3-point affine transform maps garment anchors -> body landmarks, so the
//    garment follows position, scale, rotation and lean in real time.
// No frames are uploaded anywhere.

const MP_VERSION = '0.10.14';
const MP_BASE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}`;
const MODEL = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task';
const DEFAULT_ANCHORS = { ls: [0.7, 0.15], rs: [0.3, 0.15], hip: [0.5, 0.8] };

export class PoseEngine {
  constructor() { this.landmarker = null; this.mode = 'VIDEO'; this.lastTs = -1; }

  async init() {
    const vision = await import(/* webpackIgnore: true */ `${MP_BASE}/vision_bundle.mjs`);
    const fileset = await vision.FilesetResolver.forVisionTasks(`${MP_BASE}/wasm`);
    const make = (delegate) => vision.PoseLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: MODEL, delegate },
      runningMode: 'VIDEO', numPoses: 1,
      minPoseDetectionConfidence: 0.5, minPosePresenceConfidence: 0.5, minTrackingConfidence: 0.5,
    });
    try { this.landmarker = await make('GPU'); } catch { this.landmarker = await make('CPU'); }
    return this;
  }

  async setMode(mode) {
    if (this.mode === mode || !this.landmarker) return;
    await this.landmarker.setOptions({ runningMode: mode });
    this.mode = mode;
  }

  detectVideo(video) {
    if (!this.landmarker || video.readyState < 2) return null;
    let ts = performance.now();
    if (ts <= this.lastTs) ts = this.lastTs + 1;
    this.lastTs = ts;
    const r = this.landmarker.detectForVideo(video, ts);
    return r?.landmarks?.[0] || null;
  }

  async detectImage(image) {
    await this.setMode('IMAGE');
    const r = this.landmarker.detect(image);
    return r?.landmarks?.[0] || null;
  }
}

// Exponential smoothing for jitter-free tracking
export class Smoother {
  constructor(alpha = 0.45) { this.alpha = alpha; this.prev = null; }
  push(points) {
    if (!points) { this.prev = null; return null; }
    if (!this.prev) { this.prev = points.map((p) => ({ ...p })); return this.prev; }
    const a = this.alpha;
    this.prev = points.map((p, i) => ({ x: a * p.x + (1 - a) * this.prev[i].x, y: a * p.y + (1 - a) * this.prev[i].y, z: p.z, visibility: p.visibility }));
    return this.prev;
  }
}

// Solve the affine matrix [a c e; b d f] mapping three src points onto three dst points.
export function affineFrom3(src, dst) {
  const [[x1, y1], [x2, y2], [x3, y3]] = src;
  const det = x1 * (y2 - y3) - y1 * (x2 - x3) + (x2 * y3 - x3 * y2);
  if (Math.abs(det) < 1e-6) return null;
  const solve = (v1, v2, v3) => [
    (v1 * (y2 - y3) - y1 * (v2 - v3) + (v2 * y3 - v3 * y2)) / det,
    (x1 * (v2 - v3) - v1 * (x2 - x3) + (x2 * v3 - x3 * v2)) / det,
    (x1 * (y2 * v3 - y3 * v2) - y1 * (x2 * v3 - x3 * v2) + v1 * (x2 * y3 - x3 * y2)) / det,
  ];
  const [a, c, e] = solve(dst[0][0], dst[1][0], dst[2][0]);
  const [b, d, f] = solve(dst[0][1], dst[1][1], dst[2][1]);
  return [a, b, c, d, e, f];
}

/**
 * Where should the garment's anchors land on the canvas?
 * @param lm      pose landmarks (normalised to the source frame)
 * @param toCanvas fn mapping normalised source coords -> canvas px
 * @param opts    { scale, offsetX, offsetY }
 * returns { ls, rs, hip, quality } in canvas px, or null if shoulders aren't visible.
 */
export function bodyTargets(lm, toCanvas, { scale = 1, offsetX = 0, offsetY = 0 } = {}) {
  if (!lm) return null;
  const L = lm[11], R = lm[12], LH = lm[23], RH = lm[24];
  if (!L || !R || (L.visibility ?? 1) < 0.35 || (R.visibility ?? 1) < 0.35) return null;
  let ls = toCanvas(L.x, L.y), rs = toCanvas(R.x, R.y);
  const mid = [(ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2];
  const span = Math.hypot(ls[0] - rs[0], ls[1] - rs[1]);
  if (span < 12) return null;

  // hips: use detected hips when visible, otherwise estimate from shoulder span
  let hip, quality = 'full';
  if (LH && RH && (LH.visibility ?? 1) > 0.5 && (RH.visibility ?? 1) > 0.5) {
    const a = toCanvas(LH.x, LH.y), b = toCanvas(RH.x, RH.y);
    hip = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  } else {
    // perpendicular to the shoulder line, pointing "down" the torso
    let nx = -(ls[1] - rs[1]) / span, ny = (ls[0] - rs[0]) / span;
    if (ny < 0) { nx = -nx; ny = -ny; }
    hip = [mid[0] + nx * span * 1.45, mid[1] + ny * span * 1.45];
    quality = 'upper';
  }
  // garments sit slightly outside the shoulder joints; fit size widens around the centre
  const widen = 1.16 * scale;
  ls = [mid[0] + (ls[0] - mid[0]) * widen, mid[1] + (ls[1] - mid[1]) * widen];
  rs = [mid[0] + (rs[0] - mid[0]) * widen, mid[1] + (rs[1] - mid[1]) * widen];
  hip = [mid[0] + (hip[0] - mid[0]) * (0.96 + (scale - 1) * 0.6), mid[1] + (hip[1] - mid[1]) * (0.96 + (scale - 1) * 0.6)];
  const shift = (p) => [p[0] + offsetX, p[1] + offsetY];
  // per-side hips (widened like the shoulders) and elbows, for the Live+ mesh rig
  let lh = null, rh = null;
  if (quality === 'full') {
    const a = toCanvas(LH.x, LH.y), b = toCanvas(RH.x, RH.y);
    const hm = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], hw = 1.22 * scale;
    lh = shift([hip[0] + (a[0] - hm[0]) * hw, hip[1] + (a[1] - hm[1]) * hw]);
    rh = shift([hip[0] + (b[0] - hm[0]) * hw, hip[1] + (b[1] - hm[1]) * hw]);
  }
  const elbow = (i) => (lm[i] && (lm[i].visibility ?? 1) > 0.55 ? shift(toCanvas(lm[i].x, lm[i].y)) : null);
  const raw = { ls: shift(toCanvas(L.x, L.y)), rs: shift(toCanvas(R.x, R.y)) };
  return { ls: shift(ls), rs: shift(rs), hip: shift(hip), lh, rh, le: elbow(13), re: elbow(14), raw, quality, span };
}

/** Draw the garment so its anchors land on the body targets. */
export function drawGarment(ctx, garmentImg, anchors, targets) {
  const A = anchors || DEFAULT_ANCHORS;
  const w = garmentImg.naturalWidth || garmentImg.width, h = garmentImg.naturalHeight || garmentImg.height;
  // garment image-right shoulder is the wearer's LEFT shoulder (landmark 11)
  const src = [[A.ls[0] * w, A.ls[1] * h], [A.rs[0] * w, A.rs[1] * h], [A.hip[0] * w, A.hip[1] * h]];
  const dst = [targets.ls, targets.rs, targets.hip];
  const m = affineFrom3(src, dst);
  if (!m) return false;
  ctx.save();
  ctx.setTransform(...m);
  ctx.shadowColor = 'rgba(0,0,0,.28)';
  ctx.shadowBlur = 18;
  ctx.shadowOffsetY = 6;
  ctx.drawImage(garmentImg, 0, 0, w, h);
  ctx.restore();
  return true;
}

/** Map normalised coords of a source (video/image) drawn "cover" or "contain" into the canvas. */
export function fitMapper(srcW, srcH, cw, ch, { mode = 'cover', mirror = false } = {}) {
  const s = mode === 'cover' ? Math.max(cw / srcW, ch / srcH) : Math.min(cw / srcW, ch / srcH);
  const dw = srcW * s, dh = srcH * s, dx = (cw - dw) / 2, dy = (ch - dh) / 2;
  return {
    rect: [dx, dy, dw, dh],
    toCanvas: (x, y) => [mirror ? cw - (dx + x * dw) : dx + x * dw, dy + y * dh],
  };
}


// ============================================================================
// Fit Check Live+: mesh-warped garment that follows the body.
//  - A bilinear rig maps garment shoulders/hips onto the body's shoulders/hips, so the
//    garment leans and twists with the torso instead of staying a flat sheet.
//  - Sleeves rotate around each shoulder toward the elbow (raise an arm, the sleeve follows).
//  - The hem lags behind torso movement on a damped spring (cloth inertia).
//  - The camera's own light is blended over the garment (soft-light) so it isn't a sticker.
// Everything runs on a 2D canvas: no server, the camera never leaves the device.
// ============================================================================
const lerp = (a, b, t) => a + (b - a) * t;
const lerp2 = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t)];
const smooth = (e0, e1, x) => { const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0))); return t * t * (3 - 2 * t); };
const rot = (p, c, a) => { const s = Math.sin(a), k = Math.cos(a), x = p[0] - c[0], y = p[1] - c[1]; return [c[0] + x * k - y * s, c[1] + x * s + y * k]; };
const norm = (v) => { const l = Math.hypot(v[0], v[1]) || 1; return [v[0] / l, v[1] / l]; };
const angleBetween = (a, b) => Math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]);

export class ClothSim {
  constructor() { this.prev = null; this.off = [0, 0]; this.vel = [0, 0]; this.t = 0; }
  step(anchor, now = performance.now(), span = 240) {
    const dt = this.t ? Math.min(0.05, (now - this.t) / 1000) : 0.016; this.t = now;
    if (!this.prev) { this.prev = anchor; return this.off; }
    const mv = [(anchor[0] - this.prev[0]) / dt, (anchor[1] - this.prev[1]) / dt]; this.prev = anchor;
    const k = 60, c = 9;   // spring ~1.2 Hz, lightly damped
    for (let i = 0; i < 2; i++) {
      this.vel[i] += (-k * this.off[i] - c * this.vel[i] - mv[i] * 0.6) * dt;
      this.off[i] += this.vel[i] * dt;
    }
    const lim = span * 0.14; // swing scales with how big the body is in frame
    this.off = this.off.map((v) => Math.max(-lim, Math.min(lim, v)));
    return this.off;
  }
}

/** Build the source -> destination mapping for one garment on one frame. */
export function liveRig(anchors, w, h, t, sway = [0, 0]) {
  const A = anchors || DEFAULT_ANCHORS;
  const sLs = [A.ls[0] * w, A.ls[1] * h], sRs = [A.rs[0] * w, A.rs[1] * h], sHip = [A.hip[0] * w, A.hip[1] * h];
  const half = (sLs[0] - sRs[0]) / 2 * 0.94;
  const sLh = [sHip[0] + half, sHip[1]], sRh = [sHip[0] - half, sHip[1]];
  const across = [(t.ls[0] - t.rs[0]) / 2 * 0.94, (t.ls[1] - t.rs[1]) / 2 * 0.94];
  const dLs = t.ls, dRs = t.rs;
  const dLh = t.lh || [t.hip[0] + across[0], t.hip[1] + across[1]];
  const dRh = t.rh || [t.hip[0] - across[0], t.hip[1] - across[1]];

  // sleeve rotation: from the garment's resting sleeve direction toward the elbow
  const down = norm([(dLh[0] + dRh[0]) / 2 - (dLs[0] + dRs[0]) / 2, (dLh[1] + dRh[1]) / 2 - (dLs[1] + dRs[1]) / 2]);
  const sleeve = (sh, other, elbow, rawSh) => {
    if (!elbow) return 0;
    const out = norm([sh[0] - other[0], sh[1] - other[1]]);
    const rest = norm([down[0] * Math.cos(0.45) + out[0] * Math.sin(0.45), down[1] * Math.cos(0.45) + out[1] * Math.sin(0.45)]);
    const arm = norm([elbow[0] - (rawSh || sh)[0], elbow[1] - (rawSh || sh)[1]]);
    return Math.max(-1.1, Math.min(1.1, angleBetween(rest, arm) * 0.85));
  };
  const aL = sleeve(dLs, dRs, t.le, t.raw?.ls), aR = sleeve(dRs, dLs, t.re, t.raw?.rs);

  return (x, y) => {
    const v = (y - sRs[1]) / ((sRh[1] - sRs[1]) || 1);
    const left = lerp(sRs[0], sRh[0], v), right = lerp(sLs[0], sLh[0], v);
    const u = (x - left) / ((right - left) || 1);
    let p = lerp2(lerp2(dRs, dLs, u), lerp2(dRh, dLh, u), v);
    // sleeves: beyond the shoulder line, upper part of the garment
    const up = 1 - smooth(0.25, 0.62, v);
    if (u > 1 && aL) p = rot(p, dLs, aL * smooth(1, 1.3, u) * up);
    if (u < 0 && aR) p = rot(p, dRs, aR * smooth(0, -0.3, u) * up);
    // hem sway: lower rows lag behind the body
    const hw = smooth(0.4, 1.15, v) ** 1.4;
    return [p[0] + sway[0] * hw, p[1] + sway[1] * hw * 0.35];
  };
}

function triangle(ctx, img, s, d) {
  const m = affineFrom3(s, d); if (!m) return;
  // grow the clip by ~0.7px around the centroid to hide hairline seams between triangles
  const cx = (d[0][0] + d[1][0] + d[2][0]) / 3, cy = (d[0][1] + d[1][1] + d[2][1]) / 3;
  const g = d.map(([x, y]) => { const dx = x - cx, dy = y - cy, l = Math.hypot(dx, dy) || 1; return [x + dx / l * 0.7, y + dy / l * 0.7]; });
  ctx.save();
  ctx.beginPath(); ctx.moveTo(g[0][0], g[0][1]); ctx.lineTo(g[1][0], g[1][1]); ctx.lineTo(g[2][0], g[2][1]); ctx.closePath(); ctx.clip();
  ctx.setTransform(...m);
  ctx.drawImage(img, 0, 0);
  ctx.restore();
}

let layer = null, light = null;
/**
 * Live+ renderer. Draws the mesh-warped garment onto ctx.
 * light: { source, rect:[x,y,w,h], mirror } — the camera frame, for lighting match (optional).
 */
export function drawGarmentLive(ctx, img, anchors, targets, { sim, light: lightSrc, cols = 7, rows = 9 } = {}) {
  const w = img.naturalWidth || img.width, h = img.naturalHeight || img.height;
  if (!w || !h) return false;
  const cw = ctx.canvas.width, ch = ctx.canvas.height;
  layer ||= document.createElement('canvas');
  if (layer.width !== cw || layer.height !== ch) { layer.width = cw; layer.height = ch; }
  const g = layer.getContext('2d');
  g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cw, ch);

  const sway = sim ? sim.step(targets.hip, performance.now(), targets.span || 240) : [0, 0];
  const map = liveRig(anchors, w, h, targets, sway);
  // grid over the image (skip empty margins: garments sit inside ~5%..95%)
  const x0 = w * 0.03, x1 = w * 0.97, y0 = h * 0.03, y1 = h * 0.97;
  const P = [];
  for (let r = 0; r <= rows; r++) { const row = []; for (let c = 0; c <= cols; c++) { const x = lerp(x0, x1, c / cols), y = lerp(y0, y1, r / rows); row.push([[x, y], map(x, y)]); } P.push(row); }
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const a = P[r][c], b = P[r][c + 1], d = P[r + 1][c], e = P[r + 1][c + 1];
    triangle(g, img, [a[0], b[0], e[0]], [a[1], b[1], e[1]]);
    triangle(g, img, [a[0], e[0], d[0]], [a[1], e[1], d[1]]);
  }

  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.shadowColor = 'rgba(0,0,0,.3)'; ctx.shadowBlur = 20; ctx.shadowOffsetY = 8;
  ctx.drawImage(layer, 0, 0);
  ctx.restore();

  // lighting match: soft-light the camera's own (blurred, grey) light over the garment only
  if (lightSrc && 'filter' in ctx) {
    const lw = Math.max(1, Math.round(cw / 4)), lhh = Math.max(1, Math.round(ch / 4));
    light ||= document.createElement('canvas');
    if (light.width !== lw || light.height !== lhh) { light.width = lw; light.height = lhh; }
    const l = light.getContext('2d');
    l.setTransform(1, 0, 0, 1, 0, 0); l.globalCompositeOperation = 'source-over'; l.clearRect(0, 0, lw, lhh);
    l.filter = 'grayscale(1) blur(6px) contrast(1.15)';
    l.save(); if (lightSrc.mirror) { l.translate(lw, 0); l.scale(-1, 1); }
    const [rx, ry, rw, rh] = lightSrc.rect; l.drawImage(lightSrc.source, rx / 4, ry / 4, rw / 4, rh / 4); l.restore();
    l.filter = 'none'; l.globalCompositeOperation = 'destination-in'; l.drawImage(layer, 0, 0, lw, lhh);
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalCompositeOperation = 'soft-light'; ctx.globalAlpha = 0.55;
    ctx.drawImage(light, 0, 0, cw, ch); ctx.restore();
  }
  return true;
}
