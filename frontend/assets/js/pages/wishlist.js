import { mountChrome, $, productCard, icon } from '../ui.js';
import { getProducts, wishlist } from '../store.js';

await mountChrome({ page: 'wishlist' });
const grid = $('[data-grid]');
async function render() {
  const ids = wishlist.ids;
  const list = (await getProducts()).filter((p) => ids.includes(p.id));
  grid.innerHTML = list.length ? list.map((p) => productCard(p)).join('')
    : `<div class="empty" style="grid-column:1/-1">${icon.heart}<b>Nothing saved yet</b><p class="muted">Tap the heart on any piece to keep it here.</p><a class="btn" href="shop.html">Browse the drop</a></div>`;
}
addEventListener('tw:wish', render);
render();
