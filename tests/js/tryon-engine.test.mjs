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
