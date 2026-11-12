// Studio rail: garments on wire hangers that behave like cloth.
//
//  - The rail loops forever: drag the empty space / swipe / arrows / buttons, with inertia.
//  - Each garment is a damped pendulum on its hook, pushed by the rail's acceleration
//    (atan(a/g)) and air drag, plus a light breeze so nothing ever looks frozen.
//  - Grab a garment and pull: it follows your hand like real cloth (a stiff spring toward
//    the pull angle, so it lags), turns toward the pull, and stretches a touch if you pull
//    far. Let go and it swings back with the momentum you gave it.
//  - Click / tap a garment: it gets a flick and swings. "View piece" in the caption opens it
//    (Enter on a focused piece still opens it, for keyboard users).
//  - Turning shows real 3D: front and back panels sit apart with a fabric-coloured side
//    between them, and light falls off as the piece turns away.
//  - The lower half lags the swing (cloth flex). The loop sleeps when off screen.

const TAU = Math.PI * 2;
const SWING_K = (TAU * 0.9) ** 2;    // pendulum ~0.9 Hz
const SWING_C = 1.25;
const TWIST_K = (TAU * 0.62) ** 2;   // torsion ~0.62 Hz, under-damped: overshoots like a hanger
const TWIST_C = 0.95;
const GRAVITY = 12000;               // px/s^2 the garment "feels": tilt = atan(-a / g)
const AIR_DRAG = 0.00004;
const FRICTION = 3.2;
const DRIFT = -12;
const PULL_K = 230, PULL_C = 24;     // hand -> garment spring while pulling
const SWING_MAX = 0.85, TWIST_MAX = 2.6;

export function mountStudio(stage, pieces, { onFocusChange, reduced = matchMedia('(prefers-reduced-motion: reduce)').matches } = {}) {
  const track = stage.querySelector('[data-track]');
  const floor = stage.querySelector('[data-floor]');
  const hanger = `<svg class="piece__hanger" viewBox="0 0 200 92" aria-hidden="true"><path d="M100 30c0-9 8-11 8-19a8 8 0 0 0-16 0" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M100 30 L14 84 Q8 88 16 88 H184 Q192 88 186 84 Z" fill="none" stroke="currentColor" stroke-width="4.5" stroke-linejoin="round"/></svg>`;

  let items = [...pieces];
  const spacingEstimate = () => Math.max(150, Math.min(innerWidth * 0.17, 270)) * 1.08;
  while (items.length < Math.ceil((innerWidth + 600) / spacingEstimate()) + 2) items = items.concat(pieces);

  track.innerHTML = items.map((p, i) => `
    <a class="piece" draggable="false" href="${p.href}" data-i="${i}" aria-label="${p.label}" style="--c:${p.color || '#555'}" ${i >= pieces.length ? 'tabindex="-1" aria-hidden="true"' : ''}>
      <span class="piece__drop" style="--i:${i % pieces.length}">
        <span class="piece__pivot">${hanger}
          <span class="piece__flex">
            ${p.views ? `<span class="piece__twist is-tt">
              <img class="piece__front piece__v" src="${p.front}" srcset="${p.srcset || ''}" sizes="(max-width: 640px) 46vw, 260px" width="900" height="1080" alt="" draggable="false" ${i < 6 ? 'fetchpriority="high"' : 'loading="lazy"'} decoding="async">
              <img class="piece__v" src="${p.views.q}" srcset="${p.views.qset || ''}" sizes="(max-width: 640px) 46vw, 260px" width="900" height="1080" alt="" draggable="false" loading="lazy" decoding="async">
              <img class="piece__v" src="${p.views.s}" srcset="${p.views.sset || ''}" sizes="(max-width: 640px) 46vw, 260px" width="900" height="1080" alt="" draggable="false" loading="lazy" decoding="async">
              <img class="piece__v piece__v--back" src="${p.back || p.front}" width="900" height="1080" alt="" draggable="false" loading="lazy" decoding="async">
            </span>` : `<span class="piece__twist">
              <img class="piece__front" src="${p.front}" srcset="${p.srcset || ''}" sizes="(max-width: 640px) 46vw, 260px" width="900" height="1080" alt="" draggable="false" ${i < 6 ? 'fetchpriority="high"' : 'loading="lazy"'} decoding="async">
              <span class="piece__side" aria-hidden="true"></span>
              <img class="piece__back ${p.back ? '' : 'is-mirror'}" src="${p.back || p.front}" width="900" height="1080" alt="" draggable="false" loading="lazy" decoding="async">
            </span>`}
          </span>
        </span>
      </span>
    </a>`).join('');
  floor.innerHTML = items.map(() => '<i class="piece-shadow"></i>').join('');

  const els = [...track.children];
  const shadows = [...floor.children];
  // turntable pieces: real photos at 0 / 45 / 90 / 180 degrees
  const tt = els.map((el) => (el.querySelector('.is-tt') ? [...el.querySelectorAll('.piece__v')] : null));
  const KEYS = [0, Math.PI / 4, Math.PI / 2, Math.PI];
  const smooth = (a, b, x) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  function turntable(views, tw) {
    let a = Math.abs(tw) % (2 * Math.PI); if (a > Math.PI) a = 2 * Math.PI - a;   // fold to 0..180deg
    let k = 0; while (k < 2 && a > KEYS[k + 1]) k++;
    const w = smooth(0.3, 0.7, (a - KEYS[k]) / (KEYS[k + 1] - KEYS[k]));         // mostly crisp, short dissolve
    for (let v = 0; v < 4; v++) views[v].style.opacity = v === k ? (1 - w).toFixed(3) : v === k + 1 ? w.toFixed(3) : '0';
    // the angle photos show the garment's left side; turning the other way mirrors them
    views[0].parentElement.classList.toggle('is-flip', Math.sin(tw) > 0);
  }
  const st = items.map((_, i) => ({ th: 0, om: 0, tw: 0, tv: 0, fl: 0, str: 0, pull: null, phase: i * 1.7 + Math.random() * 3 }));

  let W = 0, S = 0, L = 0, total = 0, stageW = 0, railY = 0;
  function measure() {
    stageW = stage.clientWidth;
    W = els[0].offsetWidth;
    S = W * 1.08;
    L = W * 1.25;
    total = S * items.length;
    railY = stage.querySelector('.studio__rail').offsetTop;
    floor.style.top = `${Math.min(stage.clientHeight - 30, railY + W * 1.2 + stage.clientHeight * 0.07)}px`;
  }

  let offset = 0, vel = 0, lastVel = 0, accel = 0, target = null;
  let drag = null, hovering = false, visible = true, last = performance.now(), running = false, clock = 0;
  let focusIdx = -1, picked = null;

  const wrap = (x) => ((x % total) + total) % total;
  const posOf = (i) => wrap(i * S + offset) - S;
  const pivotOf = (i) => { const r = stage.getBoundingClientRect(); return [r.left + posOf(i) + W / 2, r.top + railY + 4]; };
  const centreIdx = () => {
    let best = 0, bd = Infinity; const c = stageW / 2;
    for (let i = 0; i < els.length; i++) { const d = Math.abs(posOf(i) + W / 2 - c); if (d < bd) { bd = d; best = i; } }
    return best;
  };

  function frame(now) {
    const dt = Math.min(0.033, (now - last) / 1000); last = now; clock += dt;
    if (target !== null && !(drag && drag.mode === 'rail')) {
      const k = 34, c = 2 * Math.sqrt(k);
      vel += ((target - offset) * k - vel * c) * dt;
      if (Math.abs(target - offset) < 0.5 && Math.abs(vel) < 4) { offset = target; vel = 0; target = null; }
    } else if (!(drag && drag.mode === 'rail')) {
      const idle = !hovering && !drag && visible && !reduced && Math.abs(vel) < Math.abs(DRIFT) + 4;
      vel += ((idle ? DRIFT : 0) - vel) * Math.min(1, (idle ? 1.2 : FRICTION) * dt);
    }
    if (!(drag && drag.mode === 'rail')) offset += vel * dt;
    const vSmooth = lastVel + (vel - lastVel) * Math.min(1, dt * 12);
    accel = (vSmooth - lastVel) / Math.max(dt, 0.001);
    lastVel = vSmooth;

    let energy = Math.abs(vel) > 0.5 ? 1 : 0;
    for (let i = 0; i < els.length; i++) {
      const s = st[i];
      if (!reduced) {
        // breeze: two slow incommensurate waves per piece, tiny torque
        const wind = Math.sin(clock * 0.8 + s.phase) * 0.6 + Math.sin(clock * 1.9 + s.phase * 1.3) * 0.4;
        const eq = -Math.atan(accel / GRAVITY) - vSmooth * AIR_DRAG;
        if (s.pull) {
          // pulled by hand: stiff spring toward the pointer's angle around the hook
          s.om += (PULL_K * (s.pull.th - s.th) - PULL_C * s.om) * dt;
          s.tv += (PULL_K * 0.6 * (s.pull.tw - s.tw) - PULL_C * 0.8 * s.tv) * dt;
          s.str += (s.pull.str - s.str) * Math.min(1, dt * 14);
        } else {
          s.om += (-SWING_K * (s.th - eq) - SWING_C * s.om + wind * 0.55) * dt;
          s.tv += (-TWIST_K * s.tw - TWIST_C * s.tv + wind * 0.35) * dt;
          s.str += (0 - s.str) * Math.min(1, dt * 8);
        }
        s.th = Math.max(-SWING_MAX, Math.min(SWING_MAX, s.th + s.om * dt));
        s.tw = Math.max(-TWIST_MAX, Math.min(TWIST_MAX, s.tw + s.tv * dt));
        // cloth flex: the hem lags the swing
        s.fl += (-s.om * 0.16 - s.fl) * Math.min(1, dt * 9);
      } else { s.th = 0; s.tw = 0; s.fl = 0; s.str = 0; }
      if (Math.abs(s.om) > 0.004 || Math.abs(s.tv) > 0.01 || Math.abs(s.tw) > 0.01 || s.pull) energy = 1;

      const x = posOf(i);
      const el = els[i];
      el.style.transform = `translate3d(${x.toFixed(1)}px,0,0)`;
      el.style.setProperty('--th', `${s.th.toFixed(4)}rad`);
      el.style.setProperty('--tw', `${s.tw.toFixed(4)}rad`);
      el.style.setProperty('--fl', `${s.fl.toFixed(4)}rad`);
      el.style.setProperty('--str', (1 + s.str).toFixed(4));
      const cos = Math.cos(s.tw);
      el.style.setProperty('--shade', (0.62 + 0.38 * Math.abs(cos)).toFixed(3)); // light falls off as it turns
      el.classList.toggle('is-back', cos < 0);
      el.style.setProperty('--hc', Math.max(0.1, Math.abs(cos)).toFixed(3)); // the hanger turns with the garment
      el.classList.toggle('is-turning', Math.abs(cos) < 0.97);
      if (tt[i]) turntable(tt[i], s.tw);
      const sx = x + W / 2 + Math.sin(s.th) * L * 1.1;
      const sw = W * (0.36 + 0.56 * Math.abs(cos));
      shadows[i].style.transform = `translate3d(${(sx - sw / 2).toFixed(1)}px,0,0) scaleX(${(sw / W).toFixed(3)})`;
    }

    const ci = picked ?? (centreIdx() % pieces.length);
    if (ci !== focusIdx) { focusIdx = ci; onFocusChange?.(ci); }

    if (energy || drag || target !== null || (!reduced && visible)) requestAnimationFrame(frame);
    else running = false;
  }
  function wake() { if (!running) { running = true; last = performance.now(); requestAnimationFrame(frame); } }

  // ---- input
  let suppressClick = false;
  stage.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const piece = e.target.closest('.piece');
    const onCloth = piece && e.target.closest('.piece__twist, .piece__hanger');
    suppressClick = false;
    const i = piece ? Number(piece.dataset.i) : -1;
    drag = { id: e.pointerId, type: e.pointerType, x: e.clientX, y: e.clientY, last: e.clientX, t: performance.now(), mode: onCloth ? 'pull' : 'rail', idx: i, decided: false, tw0: i >= 0 ? st[i].tw : 0 };
    if (onCloth) {
      const [px, py] = pivotOf(i);
      drag.reach = Math.max(W * 0.4, Math.hypot(e.clientX - px, e.clientY - py)); // where on the cloth you grabbed
    }
    target = null; wake();
  });
  addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.decided) {
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
      if (drag.type !== 'mouse' && Math.abs(dy) > Math.abs(dx) * 1.2) { drag = null; return; } // vertical swipe scrolls the page
      drag.decided = true; suppressClick = true; stage.classList.add('is-dragging');
      try { stage.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    }
    const now = performance.now();
    if (drag.mode === 'pull') {
      const s = st[drag.idx];
      const [px, py] = pivotOf(drag.idx);
      const hx = e.clientX - px, hy = Math.max(10, e.clientY - py);
      const dist = Math.hypot(hx, hy);
      s.pull = {
        th: Math.max(-SWING_MAX, Math.min(SWING_MAX, -Math.atan2(hx, hy))),   // CSS rotate(+) swings the hem left
        tw: Math.max(-TWIST_MAX, Math.min(TWIST_MAX, drag.tw0 + dx * 0.011)),  // pulling sideways turns it
        str: Math.max(0, Math.min(0.06, (dist - drag.reach) / drag.reach * 0.25)),
      };
      hovering = true;
    } else {
      const step = e.clientX - drag.last;
      offset += step;
      vel = vel * 0.6 + (step / Math.max(0.008, (now - drag.t) / 1000)) * 0.4;
    }
    drag.last = e.clientX; drag.t = now;
  });
  const release = (e) => {
    if (!drag || (e && e.pointerId !== drag.id)) return;
    if (drag.mode === 'pull' && drag.idx >= 0) {
      const s = st[drag.idx]; s.pull = null;           // keeps its momentum and swings back
      s.om = Math.max(-6, Math.min(6, s.om)); s.tv = Math.max(-10, Math.min(10, s.tv));
      hovering = false;
    } else vel = Math.max(-2600, Math.min(2600, vel));
    drag = null; stage.classList.remove('is-dragging'); wake();
  };
  addEventListener('pointerup', release);
  addEventListener('pointercancel', release);

  // click / tap = flick it (keyboard Enter, detail === 0, still opens the product)
  stage.addEventListener('click', (e) => {
    const piece = e.target.closest('.piece');
    if (suppressClick) { e.preventDefault(); e.stopPropagation(); suppressClick = false; return; }
    if (!piece || e.detail === 0) return;
    e.preventDefault();
    const i = Number(piece.dataset.i), s = st[i];
    const r = piece.getBoundingClientRect();
    const side = e.clientX < r.left + r.width / 2 ? -1 : 1;  // flick away from where you hit it
    s.om += -side * (1.5 + Math.random() * 0.6);
    s.tv += side * (2.2 + Math.random() * 1.2);
    picked = i % pieces.length; focusIdx = -1;
    setTimeout(() => { if (picked === i % pieces.length) picked = null; }, 6000);
    wake();
  }, true);

  stage.addEventListener('wheel', (e) => {
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
    e.preventDefault(); target = null; vel += -e.deltaX * 6; wake();
  }, { passive: false });

  stage.addEventListener('pointerover', (e) => {
    const piece = e.target.closest('.piece'); if (!piece || e.pointerType !== 'mouse' || drag) return;
    hovering = true; const s = st[Number(piece.dataset.i)];
    if (Math.abs(s.om) < 0.2) s.om += (e.movementX >= 0 ? -1 : 1) * 0.4;  // brushing past it
    wake();
  });
  stage.addEventListener('pointerleave', () => { if (!drag) hovering = false; wake(); });

  const stepBy = (dir) => { target = (target ?? offset) - dir * S; picked = null; wake(); };
  stage.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight') { e.preventDefault(); stepBy(1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); stepBy(-1); }
  });
  track.addEventListener('focusin', (e) => {
    const piece = e.target.closest('.piece'); if (!piece) return;
    const i = Number(piece.dataset.i);
    target = offset + (stageW / 2 - (posOf(i) + W / 2)); wake();
  });

  if (!reduced) els.forEach((el, i) => setTimeout(() => { st[i].om += (i % 2 ? -1 : 1) * (0.9 + Math.random() * 0.5); wake(); }, 260 + (i % pieces.length) * 110 + 650));

  new IntersectionObserver(([en]) => { visible = en.isIntersecting; if (visible) wake(); }).observe(stage);
  addEventListener('resize', () => { const c = centreIdx(); measure(); target = null; offset = stageW / 2 - W / 2 - c * S; wake(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) wake(); });

  measure();
  offset = stageW / 2 - W / 2 - 2 * S;
  wake();

  const api = { step: stepBy, get offset() { return offset; }, get spacing() { return S; }, state: (i) => ({ ...st[i] }) };
  window.__studio = api;
  return api;
}
