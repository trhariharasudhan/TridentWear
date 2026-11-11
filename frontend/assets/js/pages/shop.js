import { mountChrome, $, $$, productCard, params, esc, icon, inr, reveal } from '../ui.js';
import { getProducts } from '../store.js';

const q = params();
const state = {
  cat: q.get('cat') || '',
  size: q.get('size') || '',
  color: q.get('color') || '',
  fit: q.get('fit') || '',
  price: Number(q.get('max') || 2500),
  sort: q.get('sort') || 'featured',
  q: (q.get('q') || '').trim().toLowerCase(),
};
await mountChrome({ page: state.cat || 'shop' });

const grid = $('[data-grid]');
grid.innerHTML = Array(8).fill('<div class="skeleton" style="aspect-ratio:4/5"></div>').join('');
let all = [];
try { all = await getProducts(); } catch (e) {
  grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><b>Couldn't load products</b><p class="muted">${esc(e.message)}</p><button class="btn" onclick="location.reload()">Retry</button></div>`;
  throw e;
}

const uniq = (arr) => [...new Set(arr.filter(Boolean))];
const colors = uniq(all.map((p) => p.base_color)).map((c) => [c, all.find((p) => p.base_color === c)?.color_hex]);
const opts = {
  cat: [['', 'All'], ['tshirt', 'T-Shirts'], ['shirt', 'Shirts']],
  size: ['S', 'M', 'L', 'XL', 'XXL'].map((s) => [s, s]),
  color: colors.map(([c, hex]) => [c, `<i class="swatch" style="background:${esc(hex || '#ccc')}"></i>${esc(c)}`]),
  fit: uniq(all.map((p) => p.fit_type)).map((f) => [f, esc(f)]),
};
for (const [key, list] of Object.entries(opts)) {
  $(`[data-f="${key}"]`).innerHTML = list.map(([v, label]) => `<button class="chip" data-k="${key}" data-v="${esc(v)}">${label}</button>`).join('');
}
const priceInput = $('[data-f="price"]');
priceInput.value = state.price;

function apply() {
  let list = all.filter((p) =>
    (!state.cat || p.category === state.cat) &&
    (!state.size || (p.sizes || []).includes(state.size)) &&
    (!state.color || p.base_color === state.color) &&
    (!state.fit || p.fit_type === state.fit) &&
    p.price <= state.price &&
    (!state.q || [p.name, p.base_color, p.description, p.tag, p.fit_type].join(' ').toLowerCase().includes(state.q)));
  const sorters = {
    featured: (a, b) => (b.featured - a.featured) || (b.stock > 0) - (a.stock > 0) || a.id - b.id,
    new: (a, b) => b.id - a.id,
    'price-asc': (a, b) => a.price - b.price,
    'price-desc': (a, b) => b.price - a.price,
  };
  list = list.sort(sorters[state.sort] || sorters.featured);

  const title = state.q ? `Results for “${state.q}”` : state.cat === 'tshirt' ? 'T-Shirts' : state.cat === 'shirt' ? 'Shirts' : 'Shop all';
  $('[data-title]').textContent = title;
  $('[data-crumb]').textContent = title;
  document.title = `${title} · TridentWear`;
  $('[data-count]').textContent = `${list.length} ${list.length === 1 ? 'piece' : 'pieces'}`;
  $('[data-price-label]').textContent = inr(state.price);
  $$('.chip[data-k]').forEach((c) => c.classList.toggle('is-on', state[c.dataset.k] === c.dataset.v));
  $('[data-sort]').value = state.sort;

  grid.innerHTML = list.length ? list.map((p) => productCard(p)).join('')
    : `<div class="empty" style="grid-column:1/-1">${icon.search}<b>No pieces match those filters</b><button class="btn btn--ghost btn--sm" data-clear>Clear filters</button></div>`;

  const u = new URLSearchParams();
  if (state.cat) u.set('cat', state.cat); if (state.size) u.set('size', state.size); if (state.color) u.set('color', state.color);
  if (state.fit) u.set('fit', state.fit); if (state.price < 2500) u.set('max', state.price); if (state.sort !== 'featured') u.set('sort', state.sort);
  if (state.q) u.set('q', state.q);
  history.replaceState(null, '', `${location.pathname}${u.toString() ? '?' + u : ''}`);
  reveal();
}

document.addEventListener('click', (e) => {
  const chip = e.target.closest('.chip[data-k]');
  if (chip) { const k = chip.dataset.k; state[k] = state[k] === chip.dataset.v && k !== 'cat' ? '' : chip.dataset.v; apply(); }
  if (e.target.closest('[data-clear]')) { Object.assign(state, { cat: '', size: '', color: '', fit: '', price: 2500, q: '' }); priceInput.value = 2500; apply(); }
  if (e.target.closest('[data-open-filters]')) $('[data-filters]').classList.add('is-open');
  if (e.target.closest('[data-close-filters]')) $('[data-filters]').classList.remove('is-open');
});
priceInput.addEventListener('input', () => { state.price = Number(priceInput.value); apply(); });
$('[data-sort]').addEventListener('change', (e) => { state.sort = e.target.value; apply(); });
apply();
