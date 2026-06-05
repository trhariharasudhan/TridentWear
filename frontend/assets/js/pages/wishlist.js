import { get, post, request, resolveAssetUrl } from "../shared/api.js?v=20260430-v3";
import { formatCurrency, getCurrentUser, initSite, pageUrl, showToast } from "../shared/site.js?v=20260430-v3";


// DELETE helper with JSON body for wishlist removal
async function removeFromWishlist(productId) {
  return request("/api/v1/wishlist/remove", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id: productId }),
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  await initSite();
  const user = getCurrentUser();
  if (!user) {
    window.location.href = pageUrl(`/login?next=${encodeURIComponent("/wishlist")}`);
    return;
  }

  // Re-bind remove buttons with correct method
  const container = document.querySelector("[data-wishlist-grid]");
  try {
    const items = await get("/api/v1/wishlist");
    const empty = document.querySelector("[data-wishlist-empty]");
    if (!items || !items.length) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    container.innerHTML = items.map(({ product }) => `
      <article class="product-card reveal">
        <a class="product-media" href="${pageUrl(`/product?id=${product.id}`)}">
          <img src="${resolveAssetUrl(product.image)}" alt="${product.name}" loading="lazy">
        </a>
        <div class="product-body">
          <div class="product-topline">
            <span class="product-label">${product.category}</span>
            ${product.tag ? `<span class="product-tag">${product.tag}</span>` : ""}
          </div>
          <h3 class="product-name">${product.name}</h3>
          <p class="product-description">${product.description}</p>
          <div class="product-footer">
            <strong class="product-price">${formatCurrency(product.price)}</strong>
            <div class="cart-row-actions">
              <a class="btn btn-outline" href="${pageUrl(`/product?id=${product.id}`)}">View</a>
              <button class="btn btn-outline" type="button" data-remove-wish="${product.id}" style="color:var(--danger);border-color:var(--danger);">Remove ♥</button>
            </div>
          </div>
        </div>
      </article>
    `).join("");

    container.querySelectorAll("[data-remove-wish]").forEach(btn => {
      btn.addEventListener("click", async () => {
        try {
          await removeFromWishlist(Number(btn.dataset.removeWish));
          showToast("Removed from wishlist.");
          btn.closest("article").remove();
          if (!container.querySelectorAll("article").length) {
            document.querySelector("[data-wishlist-empty]").hidden = false;
          }
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });
  } catch (err) {
    container.innerHTML = `<div class="helper-note danger">${err.message}</div>`;
  }
});
