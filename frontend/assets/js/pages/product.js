import { getWithFallback } from "../shared/api.js?v=20260430-v3";
import {
  formatCurrency,
  escapeHtml,
  initSite,
  pageUrl,
  showToast,
  notify,
  resolveAssetUrl,
  productCardMarkup,
  bindProductCardActions,
  promptLoginOverlay,
  isWishlisted,
  toggleWishlist,
} from "../shared/site.js?v=20260430-v3";
import { addCartItem } from "../shared/cart.js?v=20260430-v3";
import { normalizeProduct, relatedProducts } from "../shared/catalog.js?v=20260430-v3";

/* ─── Recently viewed ─── */
const RV_KEY = "trident_recently_viewed";
const RV_MAX = 8;

function saveRecentlyViewed(product) {
  try {
    const item = {
      id: product.id,
      name: product.name,
      price: product.price,
      image: product.image,
      category: product.category,
      stock: product.stock,
    };
    let list = JSON.parse(localStorage.getItem(RV_KEY) || "[]");
    list = list.filter(p => String(p.id) !== String(product.id)); // dedupe
    list.unshift(item);
    if (list.length > RV_MAX) list = list.slice(0, RV_MAX);
    localStorage.setItem(RV_KEY, JSON.stringify(list));
  } catch (_) {}
}

let currentProduct = null;
let selectedQty = 1;

function uniqueImages(product) {
  const images = [product.image, ...(Array.isArray(product.images) ? product.images : [])]
    .filter(Boolean)
    .filter((value, index, list) => list.indexOf(value) === index);
  return images.length ? images : ["/assets/images/hero-banner.jpg"];
}

function renderGallery(product) {
  const mainImage = document.getElementById("detail-main-image");
  const thumbnails = document.getElementById("detail-thumbnails");
  if (!mainImage) return;

  const images = uniqueImages(product);
  const setImage = (image) => {
    mainImage.classList.add("is-switching");
    window.setTimeout(() => {
      mainImage.src = resolveAssetUrl(image);
      mainImage.alt = product.name || "TridentWear product";
      mainImage.classList.remove("is-switching");
    }, 120);
    thumbnails?.querySelectorAll("[data-detail-thumb]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.image === image);
    });
  };

  setImage(images[0]);

  if (!thumbnails) return;
  thumbnails.innerHTML = images.map((image, index) => `
    <button
      class="product-page-thumb ${index === 0 ? "is-active" : ""}"
      type="button"
      data-detail-thumb
      data-image="${escapeHtml(image)}"
      aria-label="View product image ${index + 1}"
    >
      <img src="${escapeHtml(resolveAssetUrl(image))}" alt="">
    </button>
  `).join("");

  thumbnails.hidden = images.length <= 1;
  thumbnails.querySelectorAll("[data-detail-thumb]").forEach((button) => {
    button.addEventListener("click", () => setImage(button.dataset.image));
  });
}

function initImageZoom() {
  const gallery = document.querySelector("[data-zoom-gallery]");
  const image = document.getElementById("detail-main-image");
  const lens = document.querySelector("[data-zoom-lens]");
  if (!gallery || !image || !lens) return;

  const resetZoom = () => {
    gallery.classList.remove("is-zooming");
    image.style.transformOrigin = "";
  };

  gallery.addEventListener("pointermove", (event) => {
    if (window.matchMedia("(max-width: 48rem)").matches) return;
    const rect = gallery.getBoundingClientRect();
    const x = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
    const y = Math.min(Math.max((event.clientY - rect.top) / rect.height, 0), 1);
    gallery.classList.add("is-zooming");
    image.style.transformOrigin = `${x * 100}% ${y * 100}%`;
    lens.style.left = `${x * 100}%`;
    lens.style.top = `${y * 100}%`;
  });

  gallery.addEventListener("pointerleave", resetZoom);
  gallery.addEventListener("pointercancel", resetZoom);
}

function renderInfoGrid(product) {
  const grid = document.getElementById("detail-info-grid");
  if (!grid) return;
  const item = normalizeProduct(product);
  const details = [
    ["Fabric", item.fabric],
    ["Weight", `${item.gsm} GSM`],
    ["Fit", item.fit_type],
    ["Neck", item.neck_type],
    ["Cloth Type", item.cloth_type],
    ["Print", item.print_method.join(" + ")],
  ].filter(([, value]) => value);

  grid.innerHTML = details.map(([label, value]) => `
    <div class="detail-info-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function renderProductHighlights(product) {
  const item = normalizeProduct(product);
  const hero = document.getElementById("detail-spec-hero");
  if (hero) {
    hero.innerHTML = [
      ["Fabric", `${item.fabric}, ${item.gsm} GSM`],
      ["Fit", `${item.fit_type} fit`],
      ["Neck", item.neck_type],
      ["Print", item.print_method.join(" + ")],
    ].map(([label, value]) => `
      <article>
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </article>
    `).join("");
  }

  const care = document.getElementById("detail-care-list");
  if (care) {
    care.innerHTML = item.wash_care.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("");
  }

  const tag = document.getElementById("detail-tag-metadata");
  if (tag) {
    const entries = [
      ["Wash-care label", item.wash_care_label ? "Included" : "Not included"],
      ["Season", item.tag_metadata.season],
      ["Style", item.tag_metadata.style],
      ["Material tag", item.tag_metadata.material],
      ["Factory", item.tag_metadata.factory],
    ];
    tag.innerHTML = entries.map(([label, value]) => `
      <div>
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `).join("");
  }
}

function initQuantity(product) {
  selectedQty = 1;
  const output = document.getElementById("detail-qty");
  const decrease = document.getElementById("qty-decrease");
  const increase = document.getElementById("qty-increase");
  const maxQty = Math.max(1, Math.min(Number(product.stock || 1), 10));

  const sync = () => {
    if (output) output.textContent = String(selectedQty);
    if (decrease) decrease.disabled = selectedQty <= 1;
    if (increase) increase.disabled = selectedQty >= maxQty;
  };

  decrease?.addEventListener("click", () => {
    selectedQty = Math.max(1, selectedQty - 1);
    sync();
  });
  increase?.addEventListener("click", () => {
    selectedQty = Math.min(maxQty, selectedQty + 1);
    sync();
  });
  sync();
}

async function loadProductDetail() {
  const urlParams = new URLSearchParams(window.location.search);
  const idStr = urlParams.get("id");
  const fallbackId = parseInt(idStr, 10);

  const statusContainer = document.getElementById("product-status");
  const contentContainer = document.getElementById("product-container");

  if (!idStr || isNaN(fallbackId)) {
    statusContainer.innerHTML = `<p style="color:var(--danger); font-weight:bold;">Product not found or invalid ID.</p><a href="${pageUrl("/products")}" class="btn btn-outline" style="margin-top:1rem;">Back to Shop</a>`;
    return;
  }

  try {
    let product = null;
    try {
      const res = await getWithFallback(["/api/v1/products/" + fallbackId]);
      if (res && res.product) product = res.product;
      else if (res && res.id) product = res;
    } catch {
      const all = await getWithFallback(["/api/v1/products", "/db/products.json"]);
      const arr = Array.isArray(all) ? all : all.products || [];
      product = arr.find(p => String(p.id) === String(fallbackId));
    }

    if (!product) {
      statusContainer.innerHTML = `<p style="color:var(--danger); font-weight:bold;">Product not found.</p><a href="${pageUrl("/products")}" class="btn btn-outline" style="margin-top:1rem;">Back to Shop</a>`;
      return;
    }

    product = normalizeProduct(product);
    currentProduct = product;

    // Track as recently viewed
    saveRecentlyViewed(product);

    // Populate data
    document.getElementById("breadcrumb-product-name").textContent = product.name;
    document.getElementById("detail-name").textContent = product.name;
    document.getElementById("detail-category").textContent = (product.category || "T-Shirt").toUpperCase();
    document.getElementById("detail-price").textContent = formatCurrency(product.price);
    document.getElementById("detail-description").textContent = product.description || "Premium quality product from TridentWear.";
    renderGallery(product);
    initImageZoom();
    renderInfoGrid(product);
    renderProductHighlights(product);
    initQuantity(product);

    // Update page title
    document.title = `${product.name} | TridentWear`;

    // Stock
    const detailStockBadge = document.getElementById("detail-stock-badge");
    const detailStockCount = document.getElementById("detail-stock-count");
    const addCartBtn = document.getElementById("detail-add-cart");

    if (product.stock > 0) {
      detailStockCount.textContent = product.stock;
    } else {
      detailStockBadge.innerHTML = "Out of Stock";
      detailStockBadge.style.background = "#fef2f2";
      detailStockBadge.style.color = "#991b1b";
      addCartBtn.disabled = true;
      addCartBtn.textContent = "Out of Stock";
    }

    // Sizes
    const sizeContainer = document.getElementById("detail-sizes");
    const sizes = product.sizes || ["S", "M", "L", "XL", "XXL"];
    const soldOut = Number(product.stock || 0) <= 0;
    sizeContainer.innerHTML = sizes.map((size, index) =>
      `<button class="size-btn ${!soldOut && index === 0 ? "is-selected" : ""}" data-size="${escapeHtml(size)}" ${soldOut ? "disabled aria-disabled=\"true\"" : ""}>${escapeHtml(size)}</button>`
    ).join("");

    sizeContainer.addEventListener("click", (e) => {
      if (e.target.classList.contains("size-btn") && !e.target.disabled) {
        sizeContainer.querySelectorAll(".size-btn").forEach(b => b.classList.remove("is-selected"));
        e.target.classList.add("is-selected");
      }
    });

    // ── REAL Add to Cart ──
    addCartBtn.addEventListener("click", () => {
      const selectedSize = sizeContainer.querySelector(".size-btn.is-selected")?.dataset.size || "M";
        const item = normalizeProduct(product);
        try {
        addCartItem(item, { size: selectedSize, qty: selectedQty, openDrawer: true });
        notify("cart", `${escapeHtml(product.name)} (${selectedSize}) added to cart!`, { product_id: product.id });
        // Animate button
        addCartBtn.classList.add("cart-success-pulse");
        addCartBtn.innerHTML = '<i class="fa-solid fa-check"></i> Added!';
        setTimeout(() => {
          addCartBtn.innerHTML = '<i class="fa-solid fa-cart-shopping"></i> Add to Cart';
          addCartBtn.classList.remove("cart-success-pulse");
        }, 1500);
      } catch (_) {
        // Not logged in
        promptLoginOverlay();
      }
    });

    // Wishlist
    const wishlistButton = document.getElementById("detail-wishlist");
    const syncWishlistButton = () => {
      const wished = isWishlisted(product.id);
      wishlistButton.classList.toggle("is-wishlisted", wished);
      wishlistButton.setAttribute("aria-pressed", String(wished));
      wishlistButton.setAttribute("aria-label", wished ? "Remove product from wishlist" : "Add product to wishlist");
      wishlistButton.innerHTML = `<i class="${wished ? "fa-solid" : "fa-regular"} fa-heart"></i>`;
      wishlistButton.style.color = wished ? "var(--primary)" : "inherit";
    };
    syncWishlistButton();
    wishlistButton.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await toggleWishlist(product.id);
        syncWishlistButton();
        btn.classList.add("wishlist-pop");
        window.setTimeout(() => btn.classList.remove("wishlist-pop"), 400);
        showToast(isWishlisted(product.id) ? "Added to wishlist" : "Removed from wishlist", "info");
      } catch (error) {
        if (error.message === "unauthorized") promptLoginOverlay();
        else showToast(error.message, "error");
      } finally {
        btn.disabled = false;
      }
    });

    // Reveal
    statusContainer.style.display = "none";
    contentContainer.style.display = "grid";

    // Load related after revealing
    loadRelatedProducts(product);
    loadReviews(product.id);

  } catch (err) {
    console.error("Error loading product detail:", err);
    statusContainer.innerHTML = `<p style="color:var(--danger); font-weight:bold;">Failed to load product details.</p><a href="${pageUrl("/products")}" class="btn btn-outline" style="margin-top:1rem;">Back to Shop</a>`;
  }
}

async function loadReviews(productId) {
  const box = document.querySelector(".detail-review-preview");
  if (!box) return;
  try {
    const data = await getWithFallback([`/api/v1/reviews/${productId}`]);
    const reviews = data.reviews || data || [];
    const count = data.count ?? reviews.length;
    const average = data.average || (reviews.length ? (reviews.reduce((sum, item) => sum + Number(item.rating || 0), 0) / reviews.length).toFixed(1) : "4.8");
    box.insertAdjacentHTML("afterend", `
      <section class="reviews-section detail-reviews" aria-labelledby="reviews-heading">
        <div class="rating-summary">
          <div><strong class="rating-avg">${average}</strong><span>${count} review${count === 1 ? "" : "s"}</span></div>
          <div class="rating-bars">${[5,4,3,2,1].map((star) => `<span>${star}★ <i style="--w:${count ? Math.round(((data.bars?.[star] || 0) / count) * 100) : 0}%"></i></span>`).join("")}</div>
        </div>
        <form class="review-form-card" data-review-form>
          <strong id="reviews-heading">Add a review</strong>
          <div class="star-input" data-star-input>${[1,2,3,4,5].map((star) => `<button type="button" data-rating="${star}" aria-label="${star} stars">★</button>`).join("")}</div>
          <textarea class="textarea" data-review-text placeholder="Share fit, fabric, and sizing notes" rows="3"></textarea>
          <button class="btn btn-primary" type="submit">Submit Review</button>
        </form>
        <div class="review-list">${reviews.length ? reviews.slice(0, 5).map((review) => `
          <article class="review-card">
            <div class="review-header"><strong>${escapeHtml(review.user_name || "Trident member")}</strong><span>${"★".repeat(Number(review.rating || 5))}</span></div>
            <p>${escapeHtml(review.review || "")}</p>
            <small>${review.verified_purchase ? "Verified purchase" : "Moderation-ready placeholder"}</small>
          </article>
        `).join("") : `<div class="empty-state compact"><strong>No reviews yet</strong><span>Be the first to leave fit notes.</span></div>`}</div>
      </section>
    `);
    bindReviewForm(productId);
  } catch (_) {}
}

function bindReviewForm(productId) {
  const form = document.querySelector("[data-review-form]");
  if (!form) return;
  let rating = 5;
  form.querySelectorAll("[data-rating]").forEach((button) => {
    button.classList.toggle("is-active", Number(button.dataset.rating) <= rating);
    button.addEventListener("click", () => {
      rating = Number(button.dataset.rating);
      form.querySelectorAll("[data-rating]").forEach((entry) => entry.classList.toggle("is-active", Number(entry.dataset.rating) <= rating));
    });
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const review = form.querySelector("[data-review-text]")?.value.trim() || "";
    try {
      const { post } = await import("../shared/api.js?v=20260430-v3");
      await post("/api/v1/reviews", { product_id: productId, rating, review });
      notify("review", "Review submitted for moderation.");
      form.reset();
    } catch (error) {
      if (error.status === 401) promptLoginOverlay();
      else showToast(error.message, "error");
    }
  });
}

/* ─── You May Also Like ─── */
async function loadRelatedProducts(currentProd) {
  const grid = document.getElementById("related-products-grid");
  if (!grid) return;

  try {
    const data = await getWithFallback(["/api/v1/products"]);
    const all = (Array.isArray(data) ? data : data.products || []);

    // Same category, exclude current
    let related = relatedProducts(all, currentProd);

    // Fallback to random if not enough
    if (related.length < 4) {
      const relatedIds = new Set(related.map((product) => String(product.id)));
      const others = all
        .map(normalizeProduct)
        .filter(p => String(p.id) !== String(currentProd.id) && !relatedIds.has(String(p.id)));
      related = [...related, ...others].slice(0, 4);
    } else {
      // Shuffle and pick 4
      related = related.sort(() => 0.5 - Math.random()).slice(0, 4);
    }

    if (!related.length) return;

    grid.innerHTML = related.map(productCardMarkup).join("");
    bindProductCardActions(grid, related);
  } catch (e) {
    console.warn("Could not load related products", e);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await initSite();
  await loadProductDetail();
});
