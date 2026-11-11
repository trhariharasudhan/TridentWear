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
  return { ls: shift(ls), rs: shift(rs), hip: shift(hip), quality, span };
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
