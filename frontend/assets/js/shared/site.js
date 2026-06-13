import { clearAuthSession, get, getAuthSession, post, resolveAssetUrl, resolveUrl, saveAuthSession, withLoading, STATIC_MODE } from "./api.js";
import { addCartItem, getCartCount, getCartSubtotal, loadCart, syncCart } from "./cart.js";
import { normalizeProduct } from "./catalog.js";
import { initErrorMonitoring } from "./error-monitor.js";

let currentUser = null;

export { resolveAssetUrl };

export function pageUrl(path = "/") {
  return resolveUrl(path);
}

/* ───────── Currency ───────── */

export function formatCurrency(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

/* ───────── HTML escaping ───────── */

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/* ───────── Toast system ───────── */

function toastStack() {
  let stack = document.querySelector("[data-toast-stack]");
  if (!stack) {
    stack = document.createElement("div");
    stack.className = "toast-stack";
    stack.setAttribute("data-toast-stack", "");
    document.body.appendChild(stack);
  }
  return stack;
}

export function showToast(message, type = "success") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  const bar = document.createElement("div");
  bar.className = "toast-progress";
  toast.appendChild(bar);
  toastStack().appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("removing");
    window.setTimeout(() => toast.remove(), 300);
  }, 2800);
}

export function notify(type, message, detail = {}) {
  window.dispatchEvent(new CustomEvent("trident:notification", { detail: { type, message, ...detail } }));
  showToast(message, type === "error" ? "error" : "success");
}

/* ───────── Skeleton loaders ───────── */

export function createSkeletonCards(count = 3) {
  return Array.from({ length: count }, () => `
    <div class="skeleton-card">
      <div class="skeleton skeleton-media"></div>
      <div class="skeleton-body">
        <div class="skeleton skeleton-line short"></div>
        <div class="skeleton skeleton-line long"></div>
        <div class="skeleton skeleton-line medium"></div>
        <div class="skeleton skeleton-line price"></div>
      </div>
    </div>
  `).join("");
}

export function createLoaderMarkup(label = "Loading...") {
  return `<div class="loader-state"><strong>${escapeHtml(label)}</strong></div>`;
}

export function createEmptyMarkup(title, copy, href = "/products", label = "Browse Products") {
  return `
    <div class="empty-state">
      <strong class="section-title">${escapeHtml(title)}</strong>
      <span class="empty-copy">${escapeHtml(copy)}</span>
      <a class="btn btn-secondary" href="${pageUrl(href)}">${escapeHtml(label)}</a>
    </div>
  `;
}

/* ───────── Product card markup ───────── */

export function productCardMarkup(product) {
  const item = normalizeProduct(product);
  const productImage = resolveAssetUrl(item.image);
  const metaSource = item.fit_type || item.subcategory || item.category || "";
  const subcategoryLabel = metaSource
    ? String(metaSource)
        .replace(/-/g, " ")
        .split(" ")
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(" ")
    : "T-Shirt";

  let scarcityTag = "";
  if (item.stock <= 0) {
    scarcityTag = `<span class="product-badge danger">Out of Stock</span>`;
  } else if (item.stock < 5) {
    scarcityTag = `<span class="product-badge danger">Only ${item.stock} Left</span>`;
  } else if (item.stock < 20) {
    scarcityTag = `<span class="product-badge warning">Fast Selling</span>`;
  } else if (item.featured) {
    scarcityTag = `<span class="product-badge primary">Trending</span>`;
  }

  const tagline = item.description ? `<p class="product-tagline">${escapeHtml(item.description.split('.')[0])}</p>` : `<p class="product-tagline">Built for movement.</p>`;

  return `
    <article class="product-card reveal" data-product-card data-product-id="${item.id}">
      <a class="product-media image-wrap" href="${pageUrl(`/product?id=${item.id}`)}" aria-label="View ${escapeHtml(item.name)}">
        ${scarcityTag}
        <button
          class="wishlist-btn product-card-wishlist ${isWishlisted(item.id) ? "is-wishlisted" : ""}"
          type="button"
          data-wishlist-toggle
          data-product-id="${item.id}"
          aria-label="${isWishlisted(item.id) ? "Remove from wishlist" : "Add to wishlist"}"
          aria-pressed="${isWishlisted(item.id) ? "true" : "false"}"
        >
          <i class="${isWishlisted(item.id) ? "fa-solid" : "fa-regular"} fa-heart" aria-hidden="true"></i>
        </button>
        <img
          src="${escapeHtml(productImage)}"
          alt="${escapeHtml(item.name)}"
          loading="lazy"
          decoding="async"
          width="640"
          height="800"
          class="product-image"
          data-product-image
        >
      </a>
      <div class="product-body">
        <div class="product-meta-row">
          <span class="product-type">${escapeHtml(subcategoryLabel)}</span>
          <span class="product-demand"><i class="fa-solid fa-fire" aria-hidden="true"></i> High Demand</span>
        </div>
        <h3 class="product-name" style="margin-top: 4px; margin-bottom: 2px;">${escapeHtml(item.name)}</h3>
        ${tagline}
        <div class="product-card-rating" aria-label="Rated 4.8 out of 5">
          <i class="fa-solid fa-star" aria-hidden="true"></i>
          <span>4.8</span>
          <small>verified fit</small>
        </div>
        <div class="product-footer" style="margin-top: 12px;">
          <strong class="product-price" style="font-size: 1.1rem;">${formatCurrency(item.price)}</strong>
          <a href="${pageUrl(`/product?id=${item.id}`)}" class="btn btn-premium-primary product-card-cta" style="padding: 0.4rem 1rem; font-size: 0.8rem; border-radius: 4px;">${item.stock <= 0 ? "Notify Me" : "Select Size"}</a>
        </div>
      </div>
    </article>
  `;
}

/* ───────── Bind product card actions ───────── */

export function bindProductCardActions(container, products) {
  const lookup = new Map(products.map((product) => {
    const item = normalizeProduct(product);
    return [String(item.id), product];
  }));

  container.querySelectorAll("[data-product-image]").forEach((image) => {
    const markLoaded = () => image.classList.add("is-loaded");
    if (image.complete) {
      markLoaded();
      return;
    }
    image.addEventListener("load", markLoaded, { once: true });
    image.addEventListener("error", markLoaded, { once: true });
  });

  // Click to open product detail page
  container.querySelectorAll("[data-product-card]").forEach((card) => {
    card.addEventListener("click", (event) => {
      if (event.target.closest("[data-wishlist-toggle]") || event.target.closest("a") || event.target.closest("[data-add-cart-mock]")) return;
      event.preventDefault();
      event.stopPropagation();
      const productId = card.dataset.productId;
      if (productId) window.location.href = pageUrl(`/product?id=${productId}`);
    });
  });

  // Add to cart — real implementation with login gate
  container.querySelectorAll("[data-add-cart-mock]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const card = btn.closest("[data-product-card]");
      const productId = card?.dataset.productId;
      const product = lookup.get(String(productId));
      if (!product) return;
      const item = normalizeProduct(product);
      try {
        addCartItem(item, { size: item.sizes?.[0] || "M", qty: 1 });
        showToast(`${item.name} added to cart!`, "success");
        // Small bounce animation on button
        btn.classList.add("cart-added");
        setTimeout(() => btn.classList.remove("cart-added"), 600);
      } catch (err) {
        // Not logged in — show login prompt
        promptLoginOverlay();
      }
    });
  });

  container.querySelectorAll("[data-wishlist-toggle]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const productId = Number(button.dataset.productId);
      const product = lookup.get(String(productId));
      button.disabled = true;
      try {
        await toggleWishlist(productId);
        button.classList.toggle("is-wishlisted", isWishlisted(productId));
        button.setAttribute("aria-pressed", String(button.classList.contains("is-wishlisted")));
        button.setAttribute("aria-label", button.classList.contains("is-wishlisted") ? "Remove from wishlist" : "Add to wishlist");
        const icon = button.querySelector("i");
        if (icon) icon.className = button.classList.contains("is-wishlisted") ? "fa-solid fa-heart" : "fa-regular fa-heart";
        button.classList.add("wishlist-pop");
        window.setTimeout(() => button.classList.remove("wishlist-pop"), 400);
        showToast(
          button.classList.contains("is-wishlisted")
            ? `${product?.name || "Item"} added to wishlist.`
            : `${product?.name || "Item"} removed from wishlist.`
        );
      } catch (error) {
        if (error.message === "unauthorized") promptLoginOverlay();
        else showToast(error.message, "error");
      } finally {
        button.disabled = false;
      }
    });
  });

  observeReveals(container);
}

function renderCartDrawer(items = loadCart()) {
  let drawer = document.querySelector("[data-cart-drawer]");
  if (!drawer) {
    drawer = document.createElement("aside");
    drawer.className = "cart-drawer";
    drawer.setAttribute("data-cart-drawer", "");
    drawer.innerHTML = `
      <div class="cart-drawer-backdrop" data-cart-drawer-close></div>
      <div class="cart-drawer-panel">
        <div class="cart-drawer-head">
          <strong>Your Cart</strong>
          <button type="button" data-cart-drawer-close aria-label="Close cart"><i class="fa-solid fa-xmark"></i></button>
        </div>
        <div class="cart-drawer-list" data-cart-drawer-list></div>
        <div class="cart-drawer-foot">
          <div><span>Subtotal</span><strong data-cart-drawer-subtotal></strong></div>
          <a class="btn btn-primary btn-full" href="${pageUrl("/checkout")}">Checkout</a>
          <a class="btn btn-outline btn-full" href="${pageUrl("/cart")}">View Cart</a>
        </div>
      </div>
    `;
    document.body.appendChild(drawer);
    drawer.querySelectorAll("[data-cart-drawer-close]").forEach((el) => el.addEventListener("click", () => drawer.classList.remove("is-open")));
  }
  const list = drawer.querySelector("[data-cart-drawer-list]");
  const subtotal = drawer.querySelector("[data-cart-drawer-subtotal]");
  if (subtotal) subtotal.textContent = formatCurrency(getCartSubtotal(items));
  if (list) {
    list.innerHTML = items.length
      ? items.map((item) => `
        <article class="cart-drawer-item">
          <img src="${resolveAssetUrl(item.image)}" alt="${escapeHtml(item.name)}">
          <div><strong>${escapeHtml(item.name)}</strong><span>Size ${escapeHtml(item.size)} x ${Number(item.qty || 1)}</span></div>
        </article>
      `).join("")
      : `<div class="empty-state compact"><strong>Your cart is empty</strong><span>Add a premium piece to start checkout.</span></div>`;
  }
  return drawer;
}

function openCartDrawer(items = loadCart()) {
  renderCartDrawer(items).classList.add("is-open");
}

function renderStickyCartCta(items = loadCart()) {
  let cta = document.querySelector("[data-sticky-cart-cta]");
  const count = getCartCount(items);
  if (!cta) {
    cta = document.createElement("a");
    cta.className = "sticky-cart-cta";
    cta.setAttribute("data-sticky-cart-cta", "");
    cta.href = pageUrl("/cart");
    document.body.appendChild(cta);
  }
  cta.hidden = count <= 0;
  cta.innerHTML = `
    <span><i class="fa-solid fa-bag-shopping" aria-hidden="true"></i>${count} item${count === 1 ? "" : "s"}</span>
    <strong>${formatCurrency(getCartSubtotal(items))}</strong>
  `;
}

// Product detail modal
function openProductDetail(product) {
  const modal = document.createElement("div");
  modal.className = "product-detail-modal";
  const images = [product.image, ...(product.images || [])].filter((v, i, a) => v && a.indexOf(v) === i);
  const typeLabel = (product.subcategory || '').replace(/-/g, ' ').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') || 'T-Shirt';

  modal.innerHTML = `
    <div class="product-detail-backdrop"></div>
    <div class="product-detail-content">
      <button class="product-detail-close" type="button" aria-label="Close"><i class="fa-solid fa-xmark"></i></button>

      <div class="product-detail-gallery">
        <div class="product-detail-main-image">
          <img src="${resolveAssetUrl(product.image)}" alt="${escapeHtml(product.name)}" id="detail-main-image">
        </div>
        ${images.length > 1 ? `<div class="product-detail-thumbnails">${images.map((img, i) => `<button class="detail-thumbnail ${i === 0 ? 'is-active' : ''}" data-image="${escapeHtml(img)}" style="background-image:url('${resolveAssetUrl(img)}')"></button>`).join('')}</div>` : ''}
      </div>

      <div class="product-detail-info">
        <div class="detail-header">
          <h2 class="detail-name">${escapeHtml(product.name)}</h2>
          <span class="detail-type">${escapeHtml(typeLabel)}</span>
        </div>
        <hr class="detail-divider">
        <div class="detail-price-block">
          <strong class="detail-price">${formatCurrency(product.price)}</strong>
          <span class="detail-price-note">Price incl. of all taxes</span>
        </div>
        <div class="detail-selection-row" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
          <div class="detail-qty-row" style="display: flex; align-items: center; gap: 0.75rem;">
            <span class="detail-qty-label" style="font-size: 0.85rem;">Quantity</span>
            <div class="detail-qty-counter">
              <button class="qty-btn qty-minus" type="button" aria-label="Decrease">&minus;</button>
              <span class="qty-value" id="detail-qty-val">1</span>
              <button class="qty-btn qty-plus" type="button" aria-label="Increase">+</button>
            </div>
          </div>
          <div class="detail-size-row" style="display: flex; align-items: center; gap: 0.75rem; flex: 1; justify-content: flex-end;">
            <div class="size-options">
              ${['S','M','L','XL'].map((size, i) => `<button class="size-btn ${i === 0 ? 'is-selected' : ''}" data-size="${escapeHtml(size)}">${escapeHtml(size)}</button>`).join('')}
            </div>
          </div>
        </div>
        <div style="display: flex; justify-content: flex-end;">
          <button class="detail-size-chart-btn" type="button" data-size-chart>SIZE CHART</button>
        </div>
        <div class="detail-size-chart-panel" hidden>
          <table class="size-chart-table">
            <thead><tr><th>Size</th><th>Chest (in)</th><th>Length (in)</th></tr></thead>
            <tbody>
              <tr><td>XS</td><td>36</td><td>27</td></tr>
              <tr><td>S</td><td>38</td><td>28</td></tr>
              <tr><td>M</td><td>40</td><td>29</td></tr>
              <tr><td>L</td><td>42</td><td>30</td></tr>
              <tr><td>XL</td><td>44</td><td>31</td></tr>
              <tr><td>XXL</td><td>46</td><td>32</td></tr>
              <tr><td>XXXL</td><td>48</td><td>33</td></tr>
            </tbody>
          </table>
        </div>
        <div class="detail-cta-row">
          <button class="detail-icon-btn detail-add-to-cart" type="button" data-product-id="${product.id}" title="Add to Cart" aria-label="Add to Cart"><i class="fa-solid fa-cart-shopping"></i></button>
          <button class="detail-icon-btn detail-wishlist-btn" type="button" data-product-id="${product.id}" title="Add to Wishlist" aria-label="Add to Wishlist"><i class="fa-regular fa-heart"></i></button>
          <button class="detail-icon-btn detail-buy-now" type="button" data-product-id="${product.id}" title="Buy Now" aria-label="Buy Now"><i class="fa-solid fa-bolt"></i></button>
        </div>
        <div class="detail-delivery">
          <strong class="detail-delivery-title">Delivery Details</strong>
          <div class="detail-pincode-row">
            <input class="detail-pincode-input" type="text" placeholder="Enter Pincode" maxlength="6" inputmode="numeric">
            <button class="detail-pincode-check" type="button">CHECK</button>
          </div>
          <div class="detail-pincode-result" hidden></div>
        </div>
        <div class="detail-return-note">
          <i class="fa-solid fa-rotate-left"></i>
          <span>Eligible for <strong>30-day return or exchange</strong>. No questions asked.</span>
        </div>
        <div class="detail-accordions">
          <div class="detail-accordion">
            <button class="detail-accordion-header" type="button" data-accordion>
              <span>Product Details</span><i class="fa-solid fa-chevron-down detail-accordion-icon"></i>
            </button>
            <div class="detail-accordion-body" hidden>
              <dl class="detail-spec-list">
                <dt>Material</dt><dd>${escapeHtml(product.material || 'Cotton')}</dd>
                <dt>GSM</dt><dd>${product.gsm || 220} GSM</dd>
                <dt>Fit Type</dt><dd>${escapeHtml(product.fit_type || 'Regular Fit')}</dd>
                <dt>Neck Type</dt><dd>${escapeHtml(product.neck_type || 'Round Neck')}</dd>
              </dl>
            </div>
          </div>
          <div class="detail-accordion">
            <button class="detail-accordion-header" type="button" data-accordion>
              <span>Product Description</span><i class="fa-solid fa-chevron-down detail-accordion-icon"></i>
            </button>
            <div class="detail-accordion-body" hidden>
              <p>${escapeHtml(product.description || 'No description available.')}</p>
            </div>
          </div>
          <div class="detail-accordion">
            <button class="detail-accordion-header" type="button" data-accordion>
              <span>Artist's Details</span><i class="fa-solid fa-chevron-down detail-accordion-icon"></i>
            </button>
            <div class="detail-accordion-body" hidden>
              <p>${escapeHtml(product.artist_details || 'Designed by the TridentWear in-house design team. Inspired by Indian heritage, culture, and street fashion.')}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
  document.body.classList.add("modal-open");
  const closeModal = () => { modal.remove(); document.body.classList.remove("modal-open"); };

  // Image gallery
  modal.querySelectorAll(".detail-thumbnail").forEach(btn => {
    btn.addEventListener("click", () => {
      const mainImg = modal.querySelector("#detail-main-image");
      mainImg.style.opacity = "0.5";
      setTimeout(() => { mainImg.src = resolveAssetUrl(btn.dataset.image); mainImg.style.opacity = "1"; }, 150);
      modal.querySelectorAll(".detail-thumbnail").forEach(b => b.classList.remove("is-active"));
      btn.classList.add("is-active");
    });
  });

  // Size
  let selectedSize = product.sizes?.[0] || 'M';
  modal.querySelectorAll(".size-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      modal.querySelectorAll(".size-btn").forEach(b => b.classList.remove("is-selected"));
      btn.classList.add("is-selected");
      selectedSize = btn.dataset.size;
    });
  });

  // Qty counter
  let qty = 1;
  const qtyValEl = modal.querySelector("#detail-qty-val");
  modal.querySelector(".qty-plus").addEventListener("click", () => { qty++; qtyValEl.textContent = qty; });
  modal.querySelector(".qty-minus").addEventListener("click", () => { if (qty > 1) qty--; qtyValEl.textContent = qty; });
  const getQty = () => Math.max(1, qty);

  // Add to cart
  modal.querySelector(".detail-add-to-cart").addEventListener("click", () => {
    try {
      const q = getQty();
      for (let i = 0; i < q; i++) addCartItem(product, { size: selectedSize });
      showToast(`${product.name} (${selectedSize}) \xd7${q} added to cart.`);
      closeModal();
    } catch (err) { 
      promptLoginOverlay();
    }
  });

  // Buy Now
  modal.querySelector(".detail-buy-now").addEventListener("click", () => {
    try {
      const q = getQty();
      for (let i = 0; i < q; i++) addCartItem(product, { size: selectedSize });
      closeModal();
      window.location.href = pageUrl("/checkout");
    } catch (err) { 
      promptLoginOverlay();
    }
  });

  // Wishlist
  modal.querySelector(".detail-wishlist-btn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    try {
      await toggleWishlist(product.id);
      const wished = localWishlist.has(Number(product.id));
      btn.classList.toggle("is-wishlisted", wished);
      btn.querySelector("i").className = wished ? "fa-solid fa-heart" : "fa-regular fa-heart";
      if (wished) showToast(`${product.name} added to wishlist.`);
    } catch (err) { 
      if (err.message === "unauthorized") promptLoginOverlay();
      else showToast(err.message, "error"); 
    }
  });

  // Pincode
  modal.querySelector(".detail-pincode-check").addEventListener("click", () => {
    const input = modal.querySelector(".detail-pincode-input");
    const result = modal.querySelector(".detail-pincode-result");
    const pin = input.value.trim();
    result.textContent = /^\d{6}$/.test(pin)
      ? `\u2713 Delivery available to ${pin}. Estimated 3\u20135 business days.`
      : "Please enter a valid 6-digit pincode.";
    result.className = `detail-pincode-result ${/^\d{6}$/.test(pin) ? 'is-success' : 'is-error'}`;
    result.hidden = false;
  });

  // Size chart toggle (inline)
  const sizeChartBtn = modal.querySelector("[data-size-chart]");
  const sizeChartPanel = modal.querySelector(".detail-size-chart-panel");
  sizeChartBtn?.addEventListener("click", () => {
    sizeChartPanel.hidden = !sizeChartPanel.hidden;
    sizeChartBtn.textContent = sizeChartPanel.hidden ? "SIZE CHART" : "HIDE CHART";
  });

  // Accordions
  modal.querySelectorAll("[data-accordion]").forEach(btn => {
    btn.addEventListener("click", () => {
      const body = btn.nextElementSibling;
      body.hidden = !body.hidden;
      btn.querySelector(".detail-accordion-icon").style.transform = body.hidden ? "" : "rotate(180deg)";
    });
  });

  modal.querySelector(".product-detail-close").addEventListener("click", closeModal);
  modal.querySelector(".product-detail-backdrop").addEventListener("click", closeModal);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); }, { once: true });
}

/* ───────── Wishlist (localStorage) ───────── */


export const localWishlist = new Set();

export function isWishlisted(id) {
  return localWishlist.has(Number(id));
}

export async function toggleWishlist(id) {
  const numId = Number(id);
  const user = getCurrentUser();
  if (!user) {
    throw new Error("unauthorized");
  }

  if (localWishlist.has(numId)) {
    localWishlist.delete(numId);
    let { request } = await import("./api.js");
    await request("/api/v1/wishlist/remove", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: numId }),
    }).catch(() => null);
  } else {
    localWishlist.add(numId);
    await post("/api/v1/wishlist/add", { product_id: numId }).catch(() => null);
  }
}

/* ───────── Quick View Modal ───────── */

function openQuickView(product) {
  let modal = document.querySelector("[data-quick-view-modal]");
  if (modal) modal.remove();

  const item = normalizeProduct(product);
  const productImage = resolveAssetUrl(item.image);

  modal = document.createElement("div");
  modal.className = "quick-view-shell";
  modal.setAttribute("data-quick-view-modal", "");
  modal.innerHTML = `
    <div class="quick-view-backdrop" data-close-quick-view></div>
    <div class="quick-view-card">
      <button class="quick-view-close" type="button" data-close-quick-view>✕</button>
      <div class="quick-view-image"><img src="${escapeHtml(productImage)}" alt="${escapeHtml(item.name)}"></div>
      <div class="quick-view-details">
        <span class="eyebrow">Quick View</span>
        <h2 class="detail-title">${escapeHtml(item.name)}</h2>
        <strong class="detail-price">${formatCurrency(item.price)}</strong>
        <p class="detail-copy">${escapeHtml(item.description)}</p>
        <div class="spec-grid">
          <article class="spec-card"><span class="label">Material</span><strong>${escapeHtml(item.material)}</strong></article>
          <article class="spec-card"><span class="label">GSM</span><strong>${item.gsm} GSM</strong></article>
          <article class="spec-card"><span class="label">Fit</span><strong>${escapeHtml(item.fit_type)}</strong></article>
          <article class="spec-card"><span class="label">Neck</span><strong>${escapeHtml(item.neck_type)}</strong></article>
        </div>
        <div style="display:flex;gap:0.75rem;flex-wrap:wrap;">
            <a class="btn btn-primary" href="${pageUrl(`/product?id=${item.id}`)}">Full Details</a>
          <button class="btn btn-secondary" type="button" data-qv-add data-product-id="${item.id}">Add to Cart</button>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
  document.body.classList.add("modal-open");

  modal.querySelectorAll("[data-close-quick-view]").forEach((el) => {
    el.addEventListener("click", () => { modal.remove(); document.body.classList.remove("modal-open"); });
  });

  const addBtn = modal.querySelector("[data-qv-add]");
  if (addBtn) {
    addBtn.addEventListener("click", () => {
      const size = item.sizes?.[0] || "M";
      addCartItem(item, { size });
      showToast(`${item.name} (${size}) added to cart.`);
      addBtn.textContent = "Added ✓";
      window.setTimeout(() => { addBtn.textContent = "Add to Cart"; }, 1200);
    });
  }
}

/* ───────── Navigation ───────── */

function setActiveNav() {
  const currentPage = document.body.dataset.page;
  document.querySelectorAll("[data-nav-link]").forEach((link) => {
    link.classList.toggle("is-active", link.dataset.navLink === currentPage);
  });
  
  /* Set active bottom nav item */
  const navMap = {
    home: "home",
    products: "shop",
    product: "shop",
    cart: "cart",
    wishlist: "wishlist",
    about: "home",
    contact: "home",
  };
  
  const bottomNav = document.querySelector(".bottom-nav");
  if (bottomNav) {
    const page = navMap[currentPage] || currentPage;
    bottomNav.querySelectorAll("[data-nav]").forEach((item) => {
      item.classList.toggle("is-active", item.dataset.nav === page);
    });
  }
}

function setCartCount(count) {
  document.querySelectorAll("[data-cart-count]").forEach((badge) => { badge.textContent = String(count); });
}

function ensureAuthLinks() {
  // Authentication links are now strictly hardcoded inside the HTML as required by layout updates.
}

function setAccountUi() {
  const firstName = currentUser?.name?.split(" ")[0] || "Profile";

  document.querySelectorAll("[data-login-link]").forEach((loginLink) => {
    if (!currentUser) {
      // Logged out state
      loginLink.innerHTML = `<i class="fa-regular fa-user"></i>`;
      loginLink.setAttribute("href", pageUrl("/login"));
      loginLink.classList.remove("is-greeting");
      loginLink.setAttribute("title", "Login / Register");
      return;
    }

    // Logged in state
    loginLink.innerHTML = `<i class="fa-solid fa-circle-user" style="color: var(--primary);"></i>`;
    loginLink.setAttribute("href", pageUrl(currentUser.role === "admin" ? "/admin" : "/profile"));
    loginLink.classList.add("is-greeting");
    loginLink.setAttribute("title", `Hello, ${firstName}`);
  });
}

function bindMobileMenu() {
  const toggle = document.querySelector("[data-mobile-toggle]");
  const nav    = document.querySelector("[data-mobile-nav]");
  const header = document.querySelector(".site-header");
  if (!toggle || !nav) return;

  const dropdowns = Array.from(nav.querySelectorAll(".nav-dropdown"));

  // Stagger delay indices on nav links for cascading reveal
  const allLinks = Array.from(nav.querySelectorAll(".nav-link, .nav-dropdown-trigger"));
  allLinks.forEach((link, i) => link.style.setProperty("--i", i));

  const setExpanded = (el, val) => el?.setAttribute("aria-expanded", String(Boolean(val)));

  const closeMenu = () => {
    nav.classList.remove("is-open");
    toggle.classList.remove("is-open");
    setExpanded(toggle, false);
    document.body.style.overflow = "";
    dropdowns.forEach(d => {
      d.classList.remove("is-open");
      setExpanded(d.querySelector(".nav-dropdown-trigger"), false);
    });
  };

  const openMenu = () => {
    nav.classList.add("is-open");
    toggle.classList.add("is-open");
    setExpanded(toggle, true);
    document.body.style.overflow = "hidden";
  };

  setExpanded(toggle, false);

  toggle.addEventListener("click", () => {
    const isOpen = nav.classList.contains("is-open");
    isOpen ? closeMenu() : openMenu();
  });

  // Dropdown accordion (mobile) / hover supported by CSS (desktop)
  dropdowns.forEach(dropdown => {
    const trigger = dropdown.querySelector(".nav-dropdown-trigger");
    if (!trigger) return;
    setExpanded(trigger, false);
    trigger.addEventListener("click", e => {
      const isMobile = window.innerWidth <= 896;
      if (!isMobile) return; // desktop uses CSS hover
      e.preventDefault();
      const willOpen = !dropdown.classList.contains("is-open");
      dropdowns.forEach(d => {
        if (d !== dropdown) {
          d.classList.remove("is-open");
          setExpanded(d.querySelector(".nav-dropdown-trigger"), false);
        }
      });
      dropdown.classList.toggle("is-open", willOpen);
      setExpanded(trigger, willOpen);
    });
  });

  // Close on regular link click
  nav.querySelectorAll("a").forEach(link => {
    if (link.classList.contains("nav-dropdown-trigger")) return;
    link.addEventListener("click", closeMenu);
  });

  // Close on outside click
  document.addEventListener("click", e => {
    if (!e.target.closest("[data-mobile-nav]") && !e.target.closest("[data-mobile-toggle]")) {
      closeMenu();
    }
  });

  // Close on Escape
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && nav.classList.contains("is-open")) closeMenu();
  });
}

function bindLogout() {
  document.querySelectorAll("[data-logout-button]").forEach((button) => {
    if (button.dataset.logoutBound === "true") {
      return;
    }

    button.dataset.logoutBound = "true";
    button.addEventListener("click", async () => {
      try {
        await post("/api/v1/auth/logout", {});
        clearAuthSession();
        currentUser = null;
        setAccountUi();
        window.setTimeout(() => {
          window.location.href = pageUrl("/login");
        }, 120);
      } catch (error) {
        showToast(error.message, "error");
      }
    });
  });
}

/* ───────── Search ───────── */

let searchProducts = [];
let searchLoadedOnce = false;

async function ensureSearchProducts() {
  if (searchLoadedOnce) return;
  try {
    const data = await get("/api/v1/products");
    searchProducts = (Array.isArray(data) ? data : data.products || []).map(normalizeProduct);
    searchLoadedOnce = true;
  } catch { searchProducts = []; }
}

function bindSearch() {
  const input = document.querySelector("[data-search-input]");
  const dropdown = document.querySelector("[data-search-results]");
  if (!input || !dropdown) return;

  let debounce = null;
  input.addEventListener("focus", ensureSearchProducts);
  input.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      const query = input.value.trim().toLowerCase();
      if (query.length < 2) { dropdown.hidden = true; return; }
      const matches = searchProducts.filter((p) =>
        p.name.toLowerCase().includes(query) || p.description.toLowerCase().includes(query)
      ).slice(0, 6);

      if (!matches.length) { 
        dropdown.innerHTML = '<div class="search-no-results">No products found for "' + escapeHtml(query) + '"</div>'; 
        dropdown.hidden = false; 
        return; 
      }
      
      dropdown.innerHTML = matches.map((p) => `
        <a class="search-result-item" href="${pageUrl(`/product?id=${p.id}`)}">
          <img class="search-result-thumb" src="${resolveAssetUrl(p.image)}" alt="${escapeHtml(p.name)}">
          <div class="search-result-info">
            <span class="search-result-name">${escapeHtml(p.name)}</span>
            <span class="search-result-price">${formatCurrency(p.price)}</span>
          </div>
        </a>
      `).join("");
      dropdown.hidden = false;
    }, 300);
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-search-wrapper]")) dropdown.hidden = true;
  });
}

/* ───────── Loaders & Skeletons ───────── */

export function startGlobalLoader() {
  if (document.querySelector(".global-loader")) return;
  const loader = document.createElement("div");
  loader.className = "global-loader";
  loader.innerHTML = '<div class="spinner"></div>';
  document.body.appendChild(loader);
}

export function endGlobalLoader() {
  const loader = document.querySelector(".global-loader");
  if (loader) {
    loader.style.opacity = "0";
    setTimeout(() => loader.remove(), 300);
  }
}



/* ───────── Back to Top ───────── */

function initBackToTop() {
  const btn = document.querySelector("[data-back-to-top]");
  if (!btn) return;
  window.addEventListener("scroll", () => { btn.classList.toggle("is-visible", window.scrollY > 400); }, { passive: true });
  btn.addEventListener("click", () => { window.scrollTo({ top: 0, behavior: "smooth" }); });
}

/* ───────── Scroll Reveal ───────── */

export function observeReveals(root = document) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.classList.add("is-visible"); observer.unobserve(entry.target); }
    });
  }, { threshold: 0.08, rootMargin: "0px 0px -40px 0px" });
  root.querySelectorAll(".reveal, .reveal-left, .reveal-right, .reveal-scale").forEach((el) => observer.observe(el));
}

/* ───────── Progress bar ───────── */

function createProgressBar() {
  let bar = document.querySelector("[data-progress-bar]");
  if (!bar) { bar = document.createElement("div"); bar.className = "progress-bar"; bar.setAttribute("data-progress-bar", ""); document.body.prepend(bar); }
  return bar;
}

export function startProgress() { const bar = createProgressBar(); bar.classList.remove("is-done"); bar.classList.add("is-active"); }
export function endProgress() { const bar = createProgressBar(); bar.classList.remove("is-active"); bar.classList.add("is-done"); window.setTimeout(() => bar.classList.remove("is-done"), 700); }

/* ───────── Newsletter ───────── */

function bindNewsletter() {
  const form = document.querySelector("[data-newsletter-form]");
  if (!form) return;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const email = form.querySelector("input[type='email']");
    if (email && email.value.trim()) { showToast("Thanks for subscribing!"); email.value = ""; }
  });
}

/* ───────── Auth state ───────── */

export async function refreshAuthState() {
  const session = getAuthSession();
  currentUser = session?.user || null;
  setAccountUi();
  if (!session?.token) return currentUser;
  try {
    const data = await get("/api/v1/auth/me");
    if (!data?.authenticated || !data.user) {
      clearAuthSession();
      currentUser = null;
    } else {
      currentUser = data.user;
      saveAuthSession({ ...session, user: currentUser });
    }
  } catch {
    clearAuthSession();
    currentUser = null;
  }
  setAccountUi();

  // Profile-setup gate: if logged in but profile not complete, redirect to setup page
  // Skip if already on profile-setup or auth pages to avoid infinite loops
  if (currentUser && currentUser.role !== "admin" && currentUser.profile_completed_status === false) {
    const page = document.body.dataset.page;
    const path = window.location.pathname;
    const isSetupPage = path.includes("profile-setup");
    const isAuthPage = page === "auth" || path.includes("login") || path.includes("register") || path.includes("verify");
    if (!isSetupPage && !isAuthPage) {
      window.location.href = pageUrl("/profile-setup");
    }
  }

  return currentUser;
}

export function getCurrentUser() { return currentUser; }

/* ───────── Navbar scroll glass effect (all pages) ───────── */
function initNavbarScroll() {
  const header = document.querySelector(".site-header");
  if (!header) return;
  const hasHero = document.querySelector(".hero-cinematic");

  const update = () => {
    const scrolled = window.scrollY > 60;
    header.classList.toggle("is-scrolled", scrolled || !hasHero);
  };
  window.addEventListener("scroll", update, { passive: true });
  update();

  // Search icon: click to expand/collapse input
  const searchWrapper = document.querySelector("[data-search-wrapper]");
  const searchIcon    = searchWrapper?.querySelector(".search-icon");
  const searchInput   = searchWrapper?.querySelector("[data-search-input]");
  if (searchWrapper && searchIcon && searchInput) {
    searchIcon.addEventListener("click", () => {
      const open = searchWrapper.classList.toggle("is-search-open");
      if (open) {
        setTimeout(() => searchInput.focus(), 50);
      }
    });
    // Collapse on outside click
    document.addEventListener("click", e => {
      if (!searchWrapper.contains(e.target)) {
        searchWrapper.classList.remove("is-search-open");
      }
    });
    // Collapse on Escape
    searchInput.addEventListener("keydown", e => {
      if (e.key === "Escape") {
        searchWrapper.classList.remove("is-search-open");
        searchInput.blur();
      }
    });
  }
}

/* ───────── Button ripple (all pages) ───────── */
function initButtonRipple() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".btn");
    if (!btn || btn.disabled) return;
    btn.querySelectorAll(".btn-ripple-wave").forEach(el => el.remove());
    const ripple = document.createElement("span");
    ripple.className = "btn-ripple-wave";
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2.5;
    ripple.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - rect.left - size / 2}px;top:${e.clientY - rect.top - size / 2}px`;
    btn.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
  });
}

/* ───────── Init ───────── */

export async function initSite() {
  // Guard, scroll reveal, glass navbar — clean global init
  document.body.classList.add("js-loaded");
  initErrorMonitoring();
  initGlobalScrollReveal();
  interceptLinks();
  initNavbarScroll();

  setActiveNav();
  await refreshAuthState();

  const user = getCurrentUser();
  if (user) {
    try {
      const items = await get("/api/v1/wishlist");
      if (items && Array.isArray(items)) {
        items.forEach(w => localWishlist.add(Number(w.product_id)));
      }
    } catch (_) {}
  }
  bindMobileMenu();
  bindLogout();
  bindSearch();
  bindNewsletter();
  initBackToTop();
  setCartCount(getCartCount(loadCart()));
  renderCartDrawer(loadCart());
  renderStickyCartCta(loadCart());
  window.addEventListener("trident:cart-change", (event) => {
    setCartCount(event.detail.count);
    renderCartDrawer(event.detail.items || loadCart());
    renderStickyCartCta(event.detail.items || loadCart());
    if (event.detail.openDrawer) openCartDrawer(event.detail.items || loadCart());
  });
  syncCart();
  bindAppComingSoon();
  observeReveals();
}

function bindAppComingSoon() {
  document.querySelectorAll("[data-app-coming-soon]").forEach(el => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      showToast("TridentWear Mobile App is coming soon! Stay tuned.", "info");
    });
  });
}

/* ───────── Global scroll reveal (runs on every page) ───────── */

function interceptLinks() {
  if (!STATIC_MODE) return;
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a');
    if (!a || !a.href || a.hasAttribute('download') || a.target === '_blank') return;
    try {
      const url = new URL(a.href, window.location.href);
      if (url.origin === window.location.origin) {
        const href = a.getAttribute('href');
        if (href && href.startsWith('/')) {
          e.preventDefault();
          window.location.href = pageUrl(href);
        }
      }
    } catch (_) {}
  });
}

function initGlobalScrollReveal() {
  const targets = document.querySelectorAll("[data-animate]");
  if (!targets.length) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.05, rootMargin: "0px 0px -20px 0px" });

  targets.forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight) {
      const delay = parseInt(el.dataset.delay || 0);
      setTimeout(() => el.classList.add("is-visible"), delay);
    } else {
      observer.observe(el);
    }
  });
}

export function promptLoginOverlay() {
  let modal = document.querySelector(".login-prompt-overlay");
  if (modal) modal.remove();
  
  modal = document.createElement("div");
  modal.className = "login-prompt-overlay";
  modal.innerHTML = `
    <div class="login-prompt-backdrop" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); z-index: 9999; backdrop-filter: blur(4px);"></div>
    <div class="login-prompt-card" style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: #fff; padding: 2rem; border-radius: 16px; width: 90%; max-width: 400px; z-index: 10000; box-shadow: 0 20px 40px rgba(0,0,0,0.2); text-align: center;">
      <div style="background:var(--primary); color:#fff; width:48px; height:48px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:1.25rem; margin:0 auto 1.5rem auto;">
        <i class="fa-solid fa-lock"></i>
      </div>
      <h3 style="font-size:1.5rem; font-weight:800; color:var(--gray-900); margin-bottom:0.75rem; letter-spacing:-0.02em;">Login to continue</h3>
      <p style="font-size:0.95rem; color:var(--gray-600); margin-bottom:2rem; line-height:1.5;">Join TridentWear to unlock your cart, wishlist, and exclusive checkout drops.</p>
      <div style="display:flex; gap:1rem; justify-content:center;">
        <button class="btn btn-outline" type="button" data-cancel style="flex:1;">Cancel</button>
        <button class="btn btn-primary" type="button" data-login style="flex:1;">Sign In</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  
  modal.querySelector("[data-cancel]").addEventListener("click", () => modal.remove());
  modal.querySelector("[data-login]").addEventListener("click", () => {
    window.location.href = pageUrl(`/login?next=${encodeURIComponent(window.location.pathname)}`);
  });
}
