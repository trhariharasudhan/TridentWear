// Studio rail: garments on wire hangers with real pendulum + torsion physics.
//
//  - The rail loops forever: drag / swipe / arrow keys / buttons move it, with inertia.
//  - Each garment is a damped pendulum hung from its hook. The rail's acceleration
//    and speed (air drag) push it, so it lags, swings and settles like the real thing.
//  - Mouse-drag a garment sideways to twist it on its hook and see the back; let go and
//    it spins back to the front (under-damped torsion spring).
//  - Floor shadows follow each garment's swing and narrow as it turns side-on.
//  - The loop sleeps when the hero is off screen or everything is at rest.

const TAU = Math.PI * 2;
const SWING_K = (TAU * 0.95) ** 2;   // pendulum natural frequency ~0.95 Hz
const SWING_C = 1.35;                // swing damping
const TWIST_K = (TAU * 0.7) ** 2;    // torsion spring ~0.7 Hz
const TWIST_C = 1.05;                // low damping: overshoots and turns back, like a hanger
const GRAVITY = 12000;               // px/s^2 felt by the garment: equilibrium tilt = atan(-a / g)
const AIR_DRAG = 0.00004;            // rad per px/s of rail speed
const FRICTION = 3.2;                // rail inertia decay (1/s)
const DRIFT = -12;                   // px/s idle drift; 0 when reduced motion

export function mountStudio(stage, pieces, { onFocusChange, reduced = matchMedia('(prefers-reduced-motion: reduce)').matches } = {}) {
  const track = stage.querySelector('[data-track]');
  const floor = stage.querySelector('[data-floor]');
  const hanger = `<svg class="piece__hanger" viewBox="0 0 200 92" aria-hidden="true"><path d="M100 30c0-9 8-11 8-19a8 8 0 0 0-16 0" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M100 30 L14 84 Q8 88 16 88 H184 Q192 88 186 84 Z" fill="none" stroke="currentColor" stroke-width="4.5" stroke-linejoin="round"/></svg>`;

  // Repeat the set until one loop is comfortably wider than the screen.
  let items = [...pieces];
  const minCount = () => Math.ceil((innerWidth + 600) / spacingEstimate()) + 2;
  function spacingEstimate() { return Math.max(150, Math.min(innerWidth * 0.17, 270)) * 1.08; }
  while (items.length < minCount()) items = items.concat(pieces);

  track.innerHTML = items.map((p, i) => `
    <a class="piece" draggable="false" href="${p.href}" data-i="${i}" aria-label="${p.label}" ${i >= pieces.length ? 'tabindex="-1" aria-hidden="true"' : ''}>
      <span class="piece__drop" style="--i:${i % pieces.length}">
        <span class="piece__pivot">${hanger}
          <span class="piece__twist">
            <img class="piece__front" src="${p.front}" srcset="${p.srcset || ''}" sizes="(max-width: 640px) 46vw, 260px" width="900" height="1080" alt="" draggable="false" ${i < 6 ? 'fetchpriority="high"' : 'loading="lazy"'} decoding="async">
            <img class="piece__back ${p.back ? '' : 'is-mirror'}" src="${p.back || p.front}" width="900" height="1080" alt="" draggable="false" loading="lazy" decoding="async">
          </span>
        </span>
      </span>
    </a>`).join('');
  floor.innerHTML = items.map(() => '<i class="piece-shadow"></i>').join('');

  const els = [...track.children];
  const shadows = [...floor.children];
  const st = items.map(() => ({ th: 0, om: 0, tw: 0, tv: 0, held: false }));

  let W = 0, S = 0, L = 0, total = 0, stageW = 0;
  function measure() {
    stageW = stage.clientWidth;
    W = els[0].offsetWidth;            // garment width from CSS
    S = W * 1.08;                      // hanger spacing
    L = W * 1.25;                      // effective pendulum length (hook to centre of mass)
    total = S * items.length;
    // floor shadows land a little below the hem, wherever the stage is
    const railY = stage.querySelector('.studio__rail').offsetTop;
    floor.style.top = `${Math.min(stage.clientHeight - 30, railY + W * 1.2 + stage.clientHeight * 0.07)}px`;
  }

  // ---- rail motion state
  let offset = 0, vel = 0, lastVel = 0, accel = 0, target = null;
  let dragging = null, hovering = false, visible = true, last = performance.now(), raf = 0, running = false;
  let focusIdx = -1;

  const wrap = (x) => ((x % total) + total) % total;
  const posOf = (i) => wrap(i * S + offset) - S;                 // left edge of piece i, in [-S, total-S)
  const centreIdx = () => {
    let best = 0, bd = Infinity; const c = stageW / 2;
    for (let i = 0; i < els.length; i++) { const d = Math.abs(posOf(i) + W / 2 - c); if (d < bd) { bd = d; best = i; } }
    return best;
  };

  function frame(now) {
    const dt = Math.min(0.033, (now - last) / 1000); last = now;
    // rail: spring to target (arrows / focus), inertia after release, idle drift otherwise
    if (target !== null && !dragging) {
      const k = 34, c = 2 * Math.sqrt(k);
      vel += ((target - offset) * k - vel * c) * dt;
      if (Math.abs(target - offset) < 0.5 && Math.abs(vel) < 4) { offset = target; vel = 0; target = null; }
    } else if (!dragging) {
      const idle = !hovering && visible && !reduced && Math.abs(vel) < Math.abs(DRIFT) + 4;
      vel += ((idle ? DRIFT : 0) - vel) * Math.min(1, (idle ? 1.2 : FRICTION) * dt);
    }
    if (!dragging) offset += vel * dt;
    // pointer events are noisy: low-pass the rail speed (~80 ms) before deriving acceleration
    const vSmooth = lastVel + (vel - lastVel) * Math.min(1, dt * 12);
    accel = (vSmooth - lastVel) / Math.max(dt, 0.001);
    lastVel = vSmooth;

    let energy = Math.abs(vel) > 0.5 ? 1 : 0;
    for (let i = 0; i < els.length; i++) {
      const s = st[i];
      if (!reduced) {
        const eq = -Math.atan(accel / GRAVITY) - vSmooth * AIR_DRAG;           // where the push wants it
        s.om += (-SWING_K * (s.th - eq) - SWING_C * s.om) * dt;
        s.th = Math.max(-0.3, Math.min(0.3, s.th + s.om * dt));
        if (!s.held) { s.tv += (-TWIST_K * s.tw - TWIST_C * s.tv) * dt; s.tw += s.tv * dt; }
      } else if (!s.held) { s.th = 0; s.tw = 0; }
      if (Math.abs(s.om) > 0.002 || Math.abs(s.th) > 0.002 || Math.abs(s.tv) > 0.01 || Math.abs(s.tw) > 0.01 || s.held) energy = 1;

      const x = posOf(i);
      const el = els[i];
      el.style.transform = `translate3d(${x.toFixed(1)}px,0,0)`;
      el.style.setProperty('--th', `${s.th.toFixed(4)}rad`);
      el.style.setProperty('--tw', `${s.tw.toFixed(4)}rad`);
      // shadow sits on the floor under the garment's centre of mass
      const cos = Math.abs(Math.cos(s.tw));
      const sx = x + W / 2 + Math.sin(s.th) * L * 1.1;
      const sw = W * (0.42 + 0.5 * cos);
      shadows[i].style.transform = `translate3d(${(sx - sw / 2).toFixed(1)}px,0,0) scaleX(${(sw / W).toFixed(3)})`;
      el.classList.toggle('is-back', Math.cos(s.tw) < 0);
    }

    const ci = centreIdx() % pieces.length;
    if (ci !== focusIdx) { focusIdx = ci; onFocusChange?.(ci); }

    if (energy || dragging || target !== null || (!reduced && visible && !hovering)) raf = requestAnimationFrame(frame);
    else running = false;
  }
  function wake() { if (!running) { running = true; last = performance.now(); raf = requestAnimationFrame(frame); } }

  // ---- input: drag the rail (anywhere), or twist a garment (mouse on a garment)
  let moved = false;
  stage.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const piece = e.target.closest('.piece');
    const twist = piece && e.pointerType === 'mouse' && e.target.closest('.piece__twist');
    moved = false;
    dragging = { id: e.pointerId, x: e.clientX, y: e.clientY, last: e.clientX, t: performance.now(), mode: twist ? 'twist' : 'rail', idx: piece ? Number(piece.dataset.i) : -1, start: piece ? st[Number(piece.dataset.i)].tw : 0, decided: false };
    target = null; wake();
  });
  addEventListener('pointermove', (e) => {
    if (!dragging || e.pointerId !== dragging.id) return;
    const dx = e.clientX - dragging.x, dy = e.clientY - dragging.y;
    if (!dragging.decided) {
      if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return;
      if (Math.abs(dy) > Math.abs(dx) && e.pointerType !== 'mouse') { dragging = null; return; } // vertical swipe = page scroll
      dragging.decided = true; moved = true; stage.classList.add('is-dragging');
      try { stage.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    }
    const now = performance.now();
    if (dragging.mode === 'twist') {
      const s = st[dragging.idx]; s.held = true;
      const next = dragging.start + dx * 0.012;
      s.tv = (next - s.tw) / Math.max(0.008, (now - dragging.t) / 1000); s.tw = next;
      s.om += (e.clientX - dragging.last) * 0.0009;                // tugging also swings it a little
    } else {
      const step = e.clientX - dragging.last;
      offset += step;
      vel = vel * 0.6 + (step / Math.max(0.008, (now - dragging.t) / 1000)) * 0.4;
    }
    dragging.last = e.clientX; dragging.t = now;
  });
  const release = (e) => {
    if (!dragging || (e && e.pointerId !== dragging.id)) return;
    if (dragging.mode === 'twist') { const s = st[dragging.idx]; s.held = false; s.tv = Math.max(-14, Math.min(14, s.tv)); }
    else vel = Math.max(-2600, Math.min(2600, vel));
    dragging = null; stage.classList.remove('is-dragging'); wake();
  };
  addEventListener('pointerup', release);
  addEventListener('pointercancel', release);
  stage.addEventListener('click', (e) => { if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; } }, true);

  // horizontal wheel / trackpad
  stage.addEventListener('wheel', (e) => {
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
    e.preventDefault(); target = null; vel += -e.deltaX * 6; wake();
  }, { passive: false });

  // hover: a light touch sets the garment swaying; the rail stops drifting
  stage.addEventListener('pointerover', (e) => {
    const piece = e.target.closest('.piece'); if (!piece || e.pointerType !== 'mouse') return;
    hovering = true; const s = st[Number(piece.dataset.i)];
    if (Math.abs(s.om) < 0.2) s.om += (e.movementX >= 0 ? 1 : -1) * 0.45;
    wake();
  });
  stage.addEventListener('pointerleave', () => { hovering = false; wake(); });

  // keyboard + buttons: glide by one hanger
  const stepBy = (dir) => { target = (target ?? offset) - dir * S; wake(); };
  stage.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight') { e.preventDefault(); stepBy(1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); stepBy(-1); }
  });
  // tabbing to a garment brings it to the centre
  track.addEventListener('focusin', (e) => {
    const piece = e.target.closest('.piece'); if (!piece) return;
    const i = Number(piece.dataset.i);
    target = offset + (stageW / 2 - (posOf(i) + W / 2)); wake();
  });

  // landing bounce after the drop-in animation
  if (!reduced) els.forEach((el, i) => setTimeout(() => { st[i].om += (i % 2 ? -1 : 1) * (0.9 + Math.random() * 0.5); wake(); }, 260 + (i % pieces.length) * 110 + 650));

  // sleep when off screen
  new IntersectionObserver(([en]) => { visible = en.isIntersecting; if (visible) wake(); }).observe(stage);
  addEventListener('resize', () => { const c = centreIdx(); measure(); target = null; offset = stageW / 2 - W / 2 - c * S; wake(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) wake(); });

  measure();
  offset = stageW / 2 - W / 2 - 2 * S; // third piece centred
  wake();

  const api = { step: stepBy, get offset() { return offset; }, get spacing() { return S; } };
  window.__studio = api; // used by e2e tests
  return api;
}
