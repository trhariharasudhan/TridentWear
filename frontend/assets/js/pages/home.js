import { mountChrome, $, $$, productCard, img, esc, icon, logoSvg, reveal, toast, inr } from '../ui.js';
import { getProducts } from '../store.js';
import { api } from '../api.js';

const HERO_SLUGS = ['essential-oversized-tee-bone-white', 'oxford-button-down-sky', 'violet-signal-tee', 'twill-overshirt-black', 'linen-camp-shirt-stone'];
const HOOK = `<svg class="hanger__hook" viewBox="0 0 120 64" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"><path d="M60 26c0-8 6-10 6-16a6 6 0 0 0-12 0"/><path d="M60 26 8 56h104L60 26Z" stroke-linejoin="round"/></svg>`;

await mountChrome({ page: 'home', overlayHeader: true });

$('[data-lockup]').insertAdjacentHTML('afterbegin', await logoSvg());
$('[data-band]').innerHTML = Array(2).fill(['Heavyweight 240 GSM', 'Gold embroidered', 'Made in India', 'Try before you buy', 'Free shipping', 'Oversized fits']
  .map((t) => `<span>${t}</span><i></i>`).join('')).join('');
$$('.promise').forEach((p) => p.insertAdjacentHTML('afterbegin', icon[p.dataset.icon]));

const products = await getProducts().catch(() => []);
const bySlug = new Map(products.map((p) => [p.slug, p]));

// ---- hero rail
const rail = $('[data-rail]');
const heroItems = HERO_SLUGS.map((s) => bySlug.get(s)).filter(Boolean);
rail.innerHTML = heroItems.map((p) => `
  <a class="hanger" href="product.html?id=${p.id}" aria-label="${esc(p.name)}">
    <div class="hanger__swing">${HOOK}<img class="hanger__img" src="${img(p.image)}" alt="${esc(p.name)} in ${esc(p.base_color)}"></div>
    <span class="hanger__label">${esc(p.name)} · ${inr(p.price)}</span>
  </a>`).join('');

// scroll parallax: rail slides, big word drifts; pointer nudges the swing
const hero = $('.hero');
const word = $('.hero__bigword');
let ticking = false;
function heroFrame() {
  ticking = false;
  const h = hero.offsetHeight;
  const p = Math.min(1, Math.max(0, scrollY / h));
  rail.style.transform = `translateX(calc(-50% - ${p * 22}vw))`;
  word.style.transform = `translate(calc(-50% + ${p * 12}vw), -50%) scale(${1 + p * 0.15})`;
}
addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(heroFrame); } }, { passive: true });
hero.addEventListener('pointermove', (e) => {
  const x = (e.clientX / innerWidth - 0.5) * 2;
  $$('.hanger__img', rail).forEach((el, i) => { el.style.transform = `translateX(${x * (6 + i * 2)}px) rotate(${x * 1.5}deg)`; });
});
hero.addEventListener('pointerleave', () => $$('.hanger__img', rail).forEach((el) => (el.style.transform = '')));

// ---- featured drop
const featured = products.filter((p) => p.featured);
$('[data-featured]').innerHTML = (featured.length ? featured : products.slice(0, 8)).map((p) => productCard(p)).join('');

// ---- lookbook
const looks = [
  ['trident-wordmark-tee-black', 'back', 'The Flagship'],
  ['linen-camp-shirt-stone', 'front', 'Summer Linen'],
  ['oxford-button-down-sky', 'front', 'Office Oxford'],
  ['essential-oversized-tee-olive', 'front', 'Utility Olive'],
  ['essential-oversized-tee-bone-white', 'back', 'Clean Bone'],
];
$('[data-look]').innerHTML = looks.map(([slug, view, label]) => {
  const p = bySlug.get(slug); if (!p) return '';
  const src = view === 'back' && p.gallery?.[1] ? img(p.gallery[1]) : img(p.image);
  return `<a class="look__tile" href="product.html?id=${p.id}"><img src="${src}" alt="${esc(p.name)}" loading="lazy"><div class="look__cap"><span>${label}</span><span>${inr(p.price)} →</span></div></a>`;
}).join('');

// ---- pinned 360 section: scrub video + reveal specs with scroll progress
const pin = $('[data-pin]');
const video = $('[data-scrub]');
const bar = $('[data-pin-bar]');
const specs = $$('[data-spec]');
let duration = 0;
video.addEventListener('loadedmetadata', () => { duration = video.duration || 8; });
video.load();
function pinFrame() {
  const r = pin.getBoundingClientRect();
  const total = pin.offsetHeight - innerHeight;
  const p = Math.min(1, Math.max(0, -r.top / total));
  bar.style.width = `${p * 100}%`;
  if (duration && Math.abs(video.currentTime - p * duration) > 0.04) video.currentTime = p * (duration - 0.05);
  specs.forEach((s, i) => s.classList.toggle('is-on', p > 0.12 + i * 0.2 && (innerWidth > 640 || p < 0.32 + i * 0.2)));
}
let pinTick = false;
addEventListener('scroll', () => { if (!pinTick) { pinTick = true; requestAnimationFrame(() => { pinTick = false; pinFrame(); }); } }, { passive: true });

// ---- newsletter (stored as a contact message so it reaches the admin inbox)
$('[data-news]').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('#news-email');
  if (!input.checkValidity()) { input.classList.add('is-invalid'); toast('Enter a valid email address', { type: 'error' }); return; }
  try {
    await api.contact({ name: 'Newsletter subscriber', email: input.value, subject: 'Newsletter signup', message: 'Please add me to the Trident list.' });
    input.value = ''; toast("You're on the list. Welcome to Trident.");
  } catch (err) { toast(err.message, { type: 'error' }); }
});

reveal();
