// node --test tests/js
import test from 'node:test';
import assert from 'node:assert/strict';
import { affineFrom3, bodyTargets, fitMapper, Smoother } from '../../frontend/assets/js/tryon-engine.js';

const apply = ([a, b, c, d, e, f], [x, y]) => [a * x + c * y + e, b * x + d * y + f];
const close = (p, q, eps = 1e-6) => assert.ok(Math.abs(p[0] - q[0]) < eps && Math.abs(p[1] - q[1]) < eps, `${p} != ${q}`);

test('affineFrom3 maps all three anchor points exactly', () => {
  const src = [[700, 180], [300, 180], [500, 960]];
  const dst = [[420, 300], [260, 310], [345, 620]];
  const m = affineFrom3(src, dst);
  src.forEach((s, i) => close(apply(m, s), dst[i]));
});

test('affineFrom3 rejects degenerate (collinear) anchors', () => {
  assert.equal(affineFrom3([[0, 0], [1, 1], [2, 2]], [[0, 0], [1, 0], [0, 1]]), null);
});

test('mirrored mapping flips x around the canvas centre', () => {
  const plain = fitMapper(640, 480, 300, 400, { mode: 'cover' });
  const mirror = fitMapper(640, 480, 300, 400, { mode: 'cover', mirror: true });
  const a = plain.toCanvas(0.25, 0.5), b = mirror.toCanvas(0.25, 0.5);
  close([a[0] + b[0], a[1]], [300, b[1]]);
});

test('contain mapping keeps the whole source inside the canvas', () => {
  const { rect } = fitMapper(1000, 500, 400, 400, { mode: 'contain' });
  assert.deepEqual(rect.map(Math.round), [0, 100, 400, 200]);
});

function pose({ hips = true } = {}) {
  const lm = Array.from({ length: 33 }, () => ({ x: 0.5, y: 0.5, visibility: 0.9 }));
  lm[11] = { x: 0.62, y: 0.3, visibility: 0.99 }; // person's left shoulder (image right)
  lm[12] = { x: 0.38, y: 0.3, visibility: 0.99 };
  lm[23] = { x: 0.58, y: 0.72, visibility: hips ? 0.95 : 0.1 };
  lm[24] = { x: 0.42, y: 0.72, visibility: hips ? 0.95 : 0.1 };
  return lm;
}
const identity = (x, y) => [x * 1000, y * 1000];

test('bodyTargets uses detected hips when visible', () => {
  const t = bodyTargets(pose(), identity);
  assert.equal(t.quality, 'full');
  close(t.hip, [500, 300 + (720 - 300) * 0.96], 1e-6); // hip midpoint, pulled 4% toward the shoulder centre
  assert.ok(t.ls[0] > t.rs[0], 'left shoulder stays on image right when not mirrored');
});

test('bodyTargets estimates hips for upper-body (selfie) framing', () => {
  const t = bodyTargets(pose({ hips: false }), identity);
  assert.equal(t.quality, 'upper');
  assert.ok(t.hip[1] > t.ls[1] + 200, 'estimated hip sits well below shoulders');
});

test('bodyTargets returns null when shoulders are not visible', () => {
  const lm = pose(); lm[11].visibility = 0.1;
  assert.equal(bodyTargets(lm, identity), null);
});

test('larger fit size widens the garment', () => {
  const m = bodyTargets(pose(), identity, { scale: 1 });
  const xl = bodyTargets(pose(), identity, { scale: 1.14 });
  assert.ok(xl.ls[0] - xl.rs[0] > m.ls[0] - m.rs[0]);
});

test('Smoother damps jitter between frames', () => {
  const s = new Smoother(0.5);
  s.push([{ x: 0, y: 0 }]);
  const out = s.push([{ x: 1, y: 1 }]);
  close([out[0].x, out[0].y], [0.5, 0.5]);
  assert.equal(s.push(null), null);
});

// ---- Live+ rig
import { liveRig, ClothSim } from '../../frontend/assets/js/tryon-engine.js';
const A = { ls: [0.7, 0.15], rs: [0.3, 0.15], hip: [0.5, 0.8] };
const near = (a, b, eps = 0.5) => Math.abs(a[0] - b[0]) < eps && Math.abs(a[1] - b[1]) < eps;
const T = { ls: [400, 200], rs: [200, 200], hip: [300, 500], lh: null, rh: null, le: null, re: null };

test('liveRig maps garment shoulder/hip anchors onto the body targets', () => {
  const map = liveRig(A, 1000, 1000, T);
  assert.ok(near(map(700, 150), T.ls), 'left shoulder');
  assert.ok(near(map(300, 150), T.rs), 'right shoulder');
  assert.ok(near(map(500, 800), T.hip), 'hip centre');
});

test('liveRig follows a leaning torso (per-side hips)', () => {
  const lean = { ...T, lh: [460, 520], rh: [260, 480] };
  const map = liveRig(A, 1000, 1000, lean);
  const half = (700 - 300) / 2 * 0.94;
  assert.ok(near(map(500 + half, 800), lean.lh) && near(map(500 - half, 800), lean.rh));
});

test('raising an arm rotates only that sleeve', () => {
  const still = liveRig(A, 1000, 1000, T);
  const raised = liveRig(A, 1000, 1000, { ...T, le: [560, 120], raw: { ls: [400, 200], rs: [200, 200] } });
  const sleeveL = [880, 200], sleeveR = [120, 200], chest = [500, 300];
  assert.ok(!near(still(...sleeveL), raised(...sleeveL), 5), 'left sleeve moved');
  assert.ok(near(still(...sleeveR), raised(...sleeveR)), 'right sleeve unchanged');
  assert.ok(near(still(...chest), raised(...chest)), 'torso unchanged');
});

test('hem sway moves the hem, not the shoulders', () => {
  const a = liveRig(A, 1000, 1000, T, [0, 0]), b = liveRig(A, 1000, 1000, T, [20, 0]);
  assert.ok(near(a(700, 150), b(700, 150)), 'shoulders fixed');
  assert.ok(b(500, 950)[0] - a(500, 950)[0] > 10, 'hem lags sideways');
});

test('ClothSim swings opposite to motion and settles', () => {
  const sim = new ClothSim(); let t = 0;
  sim.step([0, 0], t);
  for (let i = 1; i <= 6; i++) sim.step([i * 10, 0], (t += 16));
  assert.ok(sim.off[0] < 0, 'lags behind a move to the right');
  for (let i = 0; i < 400; i++) sim.step([60, 0], (t += 16));
  assert.ok(Math.abs(sim.off[0]) < 0.5, 'settles when still');
});
