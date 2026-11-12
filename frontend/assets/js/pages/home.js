import { mountChrome, $, $$, productCard, img, srcset, esc, icon, reveal, toast, inr, logoSvg, siteSettings } from '../ui.js';
import { mountStudio } from '../studio.js';
import { getProducts } from '../store.js';
import { api } from '../api.js';

// Studio rail order. Pieces with a back photo show it when twisted; shirts show a mirrored inside.
const RAIL = ['violet-signal-tee', 'oxford-button-down-sky', 'essential-oversized-tee-bone-white', 'twill-overshirt-black',
  'trident-wordmark-tee-black', 'linen-camp-shirt-stone', 'heavyweight-classic-tee-maroon', 'formal-slim-shirt-navy',
  'essential-oversized-tee-olive', 'oxford-button-down-white', 'heavyweight-classic-tee-sand', 'linen-camp-shirt-olive'];

await mountChrome({ page: 'home', overlayHeader: true });

$$('.promise').forEach((p) => p.insertAdjacentHTML('afterbegin', icon[p.dataset.icon]));
$$('[data-rail-step]').forEach((b) => (b.innerHTML = icon.arrow));

const products = await getProducts().catch(() => []);
const bySlug = new Map(products.map((p) => [p.slug, p]));
const byId = new Map(products.map((p) => [p.id, p]));
const site = await siteSettings();
if (site.hero_line) $('.studio__line').textContent = site.hero_line;
if (site.hero_text) $('.studio__brand p').textContent = site.hero_text;
if (site.drop_title) $('[data-featured]').closest('section').querySelector('.h2').textContent = site.drop_title;

// ---------------------------------------------------------------- the studio rail
$('[data-hero-mark]').outerHTML = await logoSvg();
const railProducts = site.rail?.length ? site.rail.map((id) => byId.get(id)) : RAIL.map((slug) => bySlug.get(slug));
const pieces = railProducts.filter(Boolean).map((p) => {
  const front = img(p.image);
  return { id: p.id, href: `product.html?id=${p.id}`, label: `${esc(p.name)}, ${esc(p.base_color)}, ${inr(p.price)}`,
    front, srcset: srcset(front), back: p.gallery?.[1] ? img(p.gallery[1]) : '', p };
});
const caption = $('[data-caption]');
const studio = mountStudio($('[data-stage]'), pieces, {
  onFocusChange: (i) => {
    const { p } = pieces[i];
    caption.innerHTML = `<b>${esc(p.name)}</b><span>${esc(p.base_color)} · ${inr(p.price)}</span><a href="product.html?id=${p.id}">View piece</a>`;
  },
});
$$('[data-rail-step]').forEach((b) => b.addEventListener('click', () => studio.step(Number(b.dataset.railStep))));

// ---------------------------------------------------------------- new drop
const withPhotos = products.filter((p) => /-front\.webp$/.test(p.image || '') && p.stock > 0);
const picks = ['violet-signal-tee', 'essential-oversized-tee-jet-black', 'oxford-button-down-sky', 'heavyweight-classic-tee-sand']
  .map((s) => bySlug.get(s)).filter(Boolean);
const chosen = (site.drop || []).map((id) => byId.get(id)).filter(Boolean);
const drop = (chosen.length ? chosen : picks.length === 4 ? picks : [...products.filter((p) => p.featured), ...withPhotos]).slice(0, 4);
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
