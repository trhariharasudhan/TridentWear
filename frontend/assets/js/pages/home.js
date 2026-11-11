import { mountChrome, $, $$, productCard, img, srcset, esc, icon, reveal, toast, inr } from '../ui.js';
import { getProducts } from '../store.js';
import { api } from '../api.js';

// Rail order: [slug, view]. Back view for the wordmark tee shows its print.
const RAIL = [
  ['essential-oversized-tee-bone-white', 'front'],
  ['oxford-button-down-sky', 'front'],
  ['violet-signal-tee', 'front'],
  ['trident-wordmark-tee-black', 'back'],
  ['essential-oversized-tee-olive', 'front'],
  ['oxford-button-down-white', 'front'],
  ['heavyweight-classic-tee-sand', 'front'],
  ['heavyweight-classic-tee-maroon', 'front'],
  ['essential-oversized-tee-charcoal', 'front'],
];
const HOOK = `<svg class="hanger__hook" viewBox="0 0 120 64" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" aria-hidden="true"><path d="M60 26c0-8 6-10 6-16a6 6 0 0 0-12 0"/><path d="M60 26 8 56h104L60 26Z" stroke-linejoin="round"/></svg>`;

await mountChrome({ page: 'home', overlayHeader: true });

$$('.promise').forEach((p) => p.insertAdjacentHTML('afterbegin', icon[p.dataset.icon]));
$$('[data-rail-step]').forEach((b) => (b.innerHTML = icon.arrow));
$('[data-facts]').innerHTML = [[icon.truck, 'Free shipping'], [icon.swap, '7-day exchanges'], [icon.cash, 'Cash on delivery']]
  .map(([i, t]) => `<span>${i}${t}</span>`).join('');

const products = await getProducts().catch(() => []);
const bySlug = new Map(products.map((p) => [p.slug, p]));

// ---------------------------------------------------------------- the rail
const rail = $('[data-rail]');
rail.innerHTML = RAIL.map(([slug, view], i) => {
  const p = bySlug.get(slug);
  if (!p) return '';
  const src = img((view === 'back' && p.gallery?.[1]) || p.image);
  return `<a class="hanger" style="--i:${i}" href="product.html?id=${p.id}" aria-label="${esc(p.name)}, ${esc(p.base_color)}, ${inr(p.price)}">
    <div class="hanger__swing">${HOOK}
      <img class="hanger__img" src="${src}" srcset="${srcset(src)}" sizes="(max-width: 640px) 58vw, 280px" width="900" height="1080" alt="" ${i < 4 ? 'fetchpriority="high"' : 'loading="lazy"'} decoding="async">
    </div>
    <span class="hanger__tag"><b>${esc(p.name)}</b><span>${inr(p.price)}</span></span>
  </a>`;
}).join('');

// Start centred on the third piece so both directions have something to discover.
requestAnimationFrame(() => {
  const third = rail.children[2];
  if (third) rail.scrollLeft = third.offsetLeft - (rail.clientWidth - third.offsetWidth) / 2;
});

const step = (dir) => {
  const w = rail.firstElementChild?.getBoundingClientRect().width || 240;
  rail.scrollBy({ left: dir * (w + 30), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
};
$$('[data-rail-step]').forEach((b) => b.addEventListener('click', () => step(Number(b.dataset.railStep))));
rail.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
  if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
});

// Drag to browse with a mouse (touch already scrolls natively). A real drag cancels the click.
let drag = null;
rail.addEventListener('pointerdown', (e) => {
  if (e.pointerType !== 'mouse' || e.button !== 0) return;
  drag = { x: e.clientX, left: rail.scrollLeft, moved: false };
});
addEventListener('pointermove', (e) => {
  if (!drag) return;
  const dx = e.clientX - drag.x;
  if (!drag.moved && Math.abs(dx) > 6) { drag.moved = true; rail.classList.add('is-dragging'); }
  if (drag.moved) rail.scrollLeft = drag.left - dx;
});
addEventListener('pointerup', () => {
  if (!drag) return;
  const moved = drag.moved; drag = null;
  if (moved) {
    // let snap settle on the nearest hanger after the drag
    requestAnimationFrame(() => rail.classList.remove('is-dragging'));
  }
});
rail.addEventListener('click', (e) => { if (rail.classList.contains('is-dragging')) e.preventDefault(); }, true);

// ---------------------------------------------------------------- new drop
const withPhotos = products.filter((p) => /-front\.webp$/.test(p.image || '') && p.stock > 0);
const picks = ['violet-signal-tee', 'essential-oversized-tee-jet-black', 'oxford-button-down-sky', 'heavyweight-classic-tee-sand']
  .map((s) => bySlug.get(s)).filter(Boolean);
const drop = (picks.length === 4 ? picks : [...products.filter((p) => p.featured), ...withPhotos]).slice(0, 4);
$('[data-featured]').innerHTML = drop.map((p, i) => productCard(p, { lazy: i > 1 })).join('');

// ---------------------------------------------------------------- fit check preview (tap a colour)
const demo = $('[data-fit-demo]');
const garment = $('[data-fit-garment]');
const demoPieces = ['violet-signal-tee', 'essential-oversized-tee-bone-white', 'oxford-button-down-sky', 'heavyweight-classic-tee-maroon']
  .map((s) => bySlug.get(s)).filter(Boolean);
const showPiece = (p) => {
  garment.classList.add('is-swap');
  setTimeout(() => {
    garment.src = img(p.image); garment.srcset = srcset(garment.src); garment.sizes = '320px';
    garment.alt = `${p.name} previewed on a body outline`;
    garment.onload = () => garment.classList.remove('is-swap');
  }, 180);
  $$('[data-fit-swatches] button', demo).forEach((b) => b.classList.toggle('is-on', Number(b.dataset.id) === p.id));
};
$('[data-fit-swatches]').innerHTML = demoPieces.map((p) => `<button type="button" data-id="${p.id}" aria-label="${esc(p.name)}, ${esc(p.base_color)}"><span style="background:${esc(p.color_hex)}"></span></button>`).join('');
$('[data-fit-swatches]').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if (!b) return;
  const p = demoPieces.find((x) => x.id === Number(b.dataset.id)); if (p) showPiece(p);
});
if (demoPieces[0]) { garment.src = img(demoPieces[0].image); garment.srcset = srcset(garment.src); garment.sizes = '320px'; $('[data-fit-swatches] button')?.classList.add('is-on'); }

// ---------------------------------------------------------------- newsletter (lands in the admin inbox)
$('[data-news]').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('#news-email');
  if (!input.checkValidity()) { input.classList.add('is-invalid'); toast('Enter a valid email address', { type: 'error' }); return; }
  try {
    await api.contact({ name: 'Newsletter subscriber', email: input.value, subject: 'Newsletter signup', message: 'Please add me to the Trident list.' });
    input.value = ''; toast("You're on the list. We'll email you before the next drop.");
  } catch (err) { toast(err.message, { type: 'error' }); }
});

reveal();
