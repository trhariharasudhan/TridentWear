import { get, getWithFallback } from "../shared/api.js?v=20260430-v3";
import {
  formatCurrency,
  escapeHtml,
  initSite,
  pageUrl,
  productUrl,
  showToast,
  notify,
  resolveAssetUrl,
  productCardMarkup,
  bindProductCardActions,
  promptLoginOverlay,
  isWishlisted,
  toggleWishlist,
  trackEvent,
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
      <img src="${escapeHtml(resolveAssetUrl(image))}" alt="" loading="lazy" decoding="async">
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
  const statusContainer = document.getElementById("product-status");
  const contentContainer = document.getElementById("product-container");

  // 1. Check pre-rendered product ID on <body>
  let targetId = null;
  const preRenderedIdStr = document.body.dataset.productId;
  if (preRenderedIdStr) {
    const parsed = parseInt(preRenderedIdStr, 10);
    if (!isNaN(parsed) && parsed > 0) {
      targetId = parsed;
    }
  }

  // 2. Fall back to ?id=N query parameter
  if (targetId === null) {
    const urlParams = new URLSearchParams(window.location.search);
    const idStr = urlParams.get("id");
    if (idStr) {
      const parsed = parseInt(idStr, 10);
      if (!isNaN(parsed) && parsed > 0) {
        targetId = parsed;
      }
    }
  }

  // Ensure noindex on legacy query routes
  if (!document.body.dataset.productId) {
    let robotsMeta = document.querySelector('meta[name="robots"]');
    if (!robotsMeta) {
      robotsMeta = document.createElement("meta");
      robotsMeta.name = "robots";
      robotsMeta.content = "noindex, follow";
      document.head.appendChild(robotsMeta);
    }
  }

  if (targetId === null) {
    statusContainer.innerHTML = `<p style="color:var(--danger); font-weight:bold;">Product not found or invalid ID.</p><a href="${pageUrl("/products")}" class="btn btn-outline" style="margin-top:1rem;">Back to Shop</a>`;
    return;
  }

  try {
    let product = null;
    try {
      const res = await getWithFallback(["/api/v1/products/" + targetId]);
      if (res && res.product) product = res.product;
      else if (res && res.id) product = res;
    } catch {
      const all = await getWithFallback(["/api/v1/products", "/db/products.json"]);
      const arr = Array.isArray(all) ? all : all.products || [];
      product = arr.find(p => String(p.id) === String(targetId));
    }

    if (!product) {
      statusContainer.innerHTML = `<p style="color:var(--danger); font-weight:bold;">Product not found.</p><a href="${pageUrl("/products")}" class="btn btn-outline" style="margin-top:1rem;">Back to Shop</a>`;
      return;
    }

    product = normalizeProduct(product);
    currentProduct = product;

    // Track as recently viewed
    saveRecentlyViewed(product);
    trackEvent("view_item", { items: [{ item_id: product.id, item_name: product.name, price: product.price }] });

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
        const result = addCartItem(item, { size: selectedSize, qty: selectedQty, openDrawer: true });
        if (result.addedQty === 0) {
          if (result.status === "OUT_OF_STOCK") {
            showToast("This item is currently out of stock.", "error");
          } else if (result.status === "EXCEEDED") {
            showToast(`Cannot add more. You already have the maximum available stock (${result.availableStock}) in your cart.`, "warning");
          } else if (result.status === "INVALID_QTY") {
            showToast("Please select a valid quantity.", "error");
          }
          return;
        }

        trackEvent("add_to_cart", { items: [{ item_id: product.id, item_name: product.name, price: product.price, quantity: result.addedQty, size: selectedSize }] });

        if (result.addedQty < selectedQty) {
          notify("cart", `Only ${result.addedQty} remaining in stock. Added ${result.addedQty} to cart!`, { product_id: product.id });
          showToast(`Only ${result.addedQty} remaining in stock. Added ${result.addedQty} to cart.`, "warning");
        } else {
          notify("cart", `${escapeHtml(product.name)} (${selectedSize}) added to cart!`, { product_id: product.id });
        }

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

    // Populate Sticky Mobile Cart
    const stickyBar = document.getElementById("sticky-mobile-cart");
    const stickyImg = document.getElementById("sticky-cart-img");
    const stickyTitle = document.getElementById("sticky-cart-title");
    const stickyPrice = document.getElementById("sticky-cart-price");
    const stickyBtn = document.getElementById("sticky-cart-btn");
    
    if (stickyBar && stickyImg && stickyTitle && stickyPrice && stickyBtn) {
      stickyImg.src = resolveAssetUrl(product.image || "assets/images/black-tshirt.png");
      stickyTitle.textContent = product.name;
      stickyPrice.textContent = formatCurrency(product.price);
      stickyBtn.addEventListener("click", () => {
        addCartBtn.click();
      });
      
      window.addEventListener("scroll", () => {
        if (window.innerWidth < 768) {
          const rect = addCartBtn.getBoundingClientRect();
          if (rect.bottom < 0) {
            stickyBar.style.display = "flex";
          } else {
            stickyBar.style.display = "none";
          }
        } else {
          stickyBar.style.display = "none";
        }
      }, { passive: true });
    }

    // Load related after revealing
    loadRelatedProducts(product);
    loadReviews(product.id);
    loadRecentlyViewed(product.id);
    // Only inject dynamic structured data if static schema was not pre-rendered
    const hasStaticJsonLd = Boolean(document.querySelector('script[type="application/ld+json"]:not([data-dynamic-schema])'));
    if (!hasStaticJsonLd && !document.body.dataset.productId) {
      injectSEOStructuredData(product);
    }

  } catch (err) {
    console.error("Error loading product detail:", err);
    statusContainer.innerHTML = `<p style="color:var(--danger); font-weight:bold;">Failed to load product details.</p><a href="${pageUrl("/products")}" class="btn btn-outline" style="margin-top:1rem;">Back to Shop</a>`;
  }
}

function injectSEOStructuredData(product) {
  // Remove any existing dynamic schemas
  document.querySelectorAll("[data-dynamic-schema]").forEach(el => el.remove());
  
  // 1. Breadcrumb Schema
  const breadcrumb = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {
        "@type": "ListItem",
        "position": 1,
        "name": "Home",
        "item": "https://trhariharasudhan.github.io/TridentWear/"
      },
      {
        "@type": "ListItem",
        "position": 2,
        "name": "Products",
        "item": "https://trhariharasudhan.github.io/TridentWear/products"
      },
      {
        "@type": "ListItem",
        "position": 3,
        "name": product.name,
        "item": window.location.href
      }
    ]
  };

  // 2. Product Schema
  const productSchema = {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": product.name,
    "image": [
      resolveAssetUrl(product.image || "/assets/images/black-tshirt.png")
    ],
    "description": product.description || "Premium heavyweight cotton T-shirt from TridentWear.",
    "sku": `TRI-PROD-${product.id}`,
    "brand": {
      "@type": "Brand",
      "name": "TridentWear"
    },
    "offers": {
      "@type": "Offer",
      "url": window.location.href,
      "priceCurrency": "INR",
      "price": product.price || 999,
      "itemCondition": "https://schema.org/NewCondition",
      "availability": product.stock > 0 ? "https://schema.org/InStock" : "https://schema.org/OutOfStock"
    }
  };

  const script1 = document.createElement("script");
  script1.type = "application/ld+json";
  script1.setAttribute("data-dynamic-schema", "true");
  script1.text = JSON.stringify(breadcrumb);
  document.head.appendChild(script1);

  const script2 = document.createElement("script");
  script2.type = "application/ld+json";
  script2.setAttribute("data-dynamic-schema", "true");
  script2.text = JSON.stringify(productSchema);
  document.head.appendChild(script2);
}

async function loadReviews(productId) {
  const box = document.querySelector(".detail-review-preview");
  if (!box) return;
  
  // Clean up any existing reviews section to prevent double loading
  const existingSection = document.querySelector(".reviews-section");
  if (existingSection) existingSection.remove();

  try {
    const data = await getWithFallback([`/api/v1/reviews/${productId}`]);
    const reviews = data.reviews || data || [];
    const count = data.count ?? reviews.length;
    const average = data.average || (reviews.length ? (reviews.reduce((sum, item) => sum + Number(item.rating || 0), 0) / reviews.length).toFixed(1) : "0.0");
    
    // Build distribution chart
    const distribution = { 5: 0, 4: 0, 3: 0, 2: 0, 1: 0 };
    reviews.forEach(r => {
      const star = Math.min(5, Math.max(1, Math.round(Number(r.rating || 5))));
      distribution[star]++;
    });

    box.insertAdjacentHTML("afterend", `
      <section class="reviews-section detail-reviews" aria-labelledby="reviews-heading">
        <div class="rating-summary" style="display: flex; gap: 2rem; align-items: center; margin-bottom: 2rem; flex-wrap: wrap;">
          <div style="text-align: center; background: var(--dark-hover); padding: 1.5rem; border-radius: 8px; border: 1px solid var(--gray-light); min-width: 140px;">
            <strong class="rating-avg" style="font-size: 3rem; font-weight: 800; color: #fff; display: block; line-height: 1;">${average}</strong>
            <span style="font-size: 0.85rem; color: var(--gray); margin-top: 0.5rem; display: block;">${count} review${count === 1 ? "" : "s"}</span>
            <div style="color: var(--accent); font-size: 0.95rem; margin-top: 0.25rem;">${"★".repeat(Math.round(Number(average)))}</div>
          </div>
          <div class="rating-bars" style="flex: 1; min-width: 200px;">
            ${[5,4,3,2,1].map((star) => {
              const pct = count ? Math.round((distribution[star] / count) * 100) : 0;
              return `<span>${star}★ <i style="--w:${pct}%"></i> <small style="width: 25px; text-align: right; font-size: 0.75rem; color: var(--gray);">${pct}%</small></span>`;
            }).join("")}
          </div>
        </div>

        <form class="review-form-card" data-review-form style="margin-bottom: 2.5rem;">
          <strong id="reviews-heading">Add a review</strong>
          <div class="star-input" data-star-input>${[1,2,3,4,5].map((star) => `<button type="button" data-rating="${star}" aria-label="${star} stars">★</button>`).join("")}</div>
          <textarea class="textarea" data-review-text placeholder="Share fit, fabric, and sizing notes" rows="3" required></textarea>
          
          <div class="review-photo-upload-row">
            <label for="review-photo-input" class="review-photo-label">
              <i class="fa-solid fa-camera"></i> Add Photos
            </label>
            <input type="file" id="review-photo-input" multiple accept="image/*" style="display:none;">
            <div class="review-photo-previews" id="review-photo-previews"></div>
          </div>

          <button class="btn btn-primary" type="submit">Submit Review</button>
        </form>

        <div class="review-list">${reviews.length ? reviews.map((review) => `
          <article class="review-card" style="border-bottom: 1px solid var(--gray-light); padding: 1.5rem 0; display: flex; flex-direction: column; gap: 0.5rem;">
            <div class="review-header" style="display: flex; justify-content: space-between; align-items: center;">
              <strong>${escapeHtml(review.user_name || "Trident member")}</strong>
              <span style="color: var(--accent);">${"★".repeat(Number(review.rating || 5))}${ "☆".repeat(5 - Number(review.rating || 5)) }</span>
            </div>
            <p style="margin: 0; color: #f3f4f6; font-size: 0.95rem;">${escapeHtml(review.review || "")}</p>
            ${review.images && review.images.length ? `
              <div class="review-card-photos">
                ${review.images.map(img => `<img src="${img}" class="review-card-photo" alt="Customer photo review" />`).join("")}
              </div>
            ` : ""}
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.25rem;">
              <small style="color: #6ee7b7; font-weight: 600; display: inline-flex; align-items: center; gap: 0.25rem;">
                <i class="fa-solid fa-circle-check"></i> Verified Buyer
              </small>
              <span style="color: var(--gray); font-size: 0.75rem;">•</span>
              <span style="color: var(--gray); font-size: 0.75rem;">${review.created_at ? new Date(review.created_at).toLocaleDateString("en-IN", { day: 'numeric', month: 'short', year: 'numeric' }) : "Recently"}</span>
            </div>
          </article>
        `).join("") : `<div class="empty-state compact"><strong>No reviews yet</strong><span>Be the first to leave fit notes.</span></div>`}</div>
      </section>
    `);
    
    bindReviewForm(productId);
    initReviewLightbox();
  } catch (_) {}
}

function initReviewLightbox() {
  if (!document.getElementById("lightbox-overlay")) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="lightbox-overlay" class="lightbox-overlay" role="dialog" aria-label="Review photo lightbox">
        <button class="lightbox-close" id="lightbox-close" aria-label="Close lightbox">&times;</button>
        <img class="lightbox-img" id="lightbox-img" src="" alt="Full-size review image">
      </div>
    `);
    
    const overlay = document.getElementById("lightbox-overlay");
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay || e.target.id === "lightbox-close") {
        overlay.classList.remove("is-open");
      }
    });
  }

  document.querySelectorAll(".review-card-photo").forEach(img => {
    img.addEventListener("click", () => {
      const lightboxImg = document.getElementById("lightbox-img");
      const overlay = document.getElementById("lightbox-overlay");
      lightboxImg.src = img.src;
      overlay.classList.add("is-open");
    });
  });
}

function bindReviewForm(productId) {
  const form = document.querySelector("[data-review-form]");
  if (!form) return;
  let rating = 5;
  let base64Images = [];

  form.querySelectorAll("[data-rating]").forEach((button) => {
    button.classList.toggle("is-active", Number(button.dataset.rating) <= rating);
    button.addEventListener("click", () => {
      rating = Number(button.dataset.rating);
      form.querySelectorAll("[data-rating]").forEach((entry) => entry.classList.toggle("is-active", Number(entry.dataset.rating) <= rating));
    });
  });

  const photoInput = form.querySelector("#review-photo-input");
  const previewsContainer = form.querySelector("#review-photo-previews");

  if (photoInput && previewsContainer) {
    photoInput.addEventListener("change", (e) => {
      const files = Array.from(e.target.files || []);
      previewsContainer.innerHTML = "";
      base64Images = [];

      files.forEach(file => {
        const reader = new FileReader();
        reader.onload = (event) => {
          base64Images.push(event.target.result);
          previewsContainer.insertAdjacentHTML("beforeend", `
            <img src="${event.target.result}" class="review-photo-preview-img" alt="Review thumbnail" />
          `);
        };
        reader.readAsDataURL(file);
      });
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const review = form.querySelector("[data-review-text]")?.value.trim() || "";
    try {
      const { post } = await import("../shared/api.js?v=20260430-v3");
      const res = await post("/api/v1/reviews", { 
        product_id: productId, 
        rating, 
        review, 
        images: base64Images 
      });
      notify("review", "Review submitted successfully.");
      form.reset();
      previewsContainer.innerHTML = "";
      base64Images = [];
      // Reload reviews to show the approved review immediately
      await loadReviews(productId);
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
    const all = (Array.isArray(data) ? data : data.products || []).map(normalizeProduct);

    // Same category, exclude current
    let related = relatedProducts(all, currentProd);

    // Fallback to random if not enough
    if (related.length < 4) {
      const relatedIds = new Set(related.map((product) => String(product.id)));
      const others = all
        .filter(p => String(p.id) !== String(currentProd.id) && !relatedIds.has(String(p.id)));
      related = [...related, ...others].slice(0, 4);
    } else {
      // Shuffle and pick 4
      related = related.sort(() => 0.5 - Math.random()).slice(0, 4);
    }

    if (related.length) {
      grid.innerHTML = related.map(productCardMarkup).join("");
      bindProductCardActions(grid, related);
    }

    // Initialize FBT and Trending sections
    loadFBT(currentProd, all);
    loadTrendingDrops(currentProd, all);
  } catch (e) {
    console.warn("Could not load related products", e);
  }
}

async function loadFBT(currentProd, allProducts) {
  const section = document.getElementById("fbt-section");
  const grid = document.getElementById("fbt-grid");
  if (!section || !grid) return;

  // If primary product is out of stock, do not display FBT bundle
  if (Number(currentProd.stock || 0) <= 0) {
    section.style.display = "none";
    return;
  }

  try {
    // 1. Fetch authoritative FBT offer from backend
    const resp = await get(`/api/v1/products/${currentProd.id}/fbt-offer`);
    if (!resp || !resp.success || !resp.offer) {
      section.style.display = "none";
      return;
    }

    const offer = resp.offer;
    const fbtToken = offer.token;
    const suggestedIds = (offer.suggested_product_ids || []).map(Number);
    const qualifyingIds = (offer.qualifying_product_ids || []).map(Number);
    const minDistinct = Number(offer.min_distinct_count || 2);
    const discountPct = Number(offer.discount_pct || 10.0);

    // 2. Resolve suggested products from catalog that are in stock
    const suggestedProducts = suggestedIds
      .map(id => allProducts.find(p => Number(p.id) === id))
      .filter(p => p && Number(p.stock || 0) > 0);

    if (suggestedProducts.length < 1) {
      section.style.display = "none";
      return;
    }

    section.style.display = "block";

    const imgPrimary = resolveAssetUrl(currentProd.image || "assets/images/black-tshirt.png");

    // 3. Render primary card + complementary product cards + offer summary box
    let cardsHtml = `
      <!-- Primary Product -->
      <div class="fbt-card" data-fbt-item="${currentProd.id}" data-price="${currentProd.price}" data-primary="true">
        <img src="${imgPrimary}" class="fbt-card-img" alt="${escapeHtml(currentProd.name)}">
        <label style="display:flex; align-items:center; font-size:0.85rem; color:#fff; cursor:default;">
          <input type="checkbox" checked disabled class="fbt-card-checkbox fbt-item-chk" data-item-id="${currentProd.id}"> <strong>This Item</strong>
        </label>
        <span class="fbt-card-title" title="${escapeHtml(currentProd.name)}">${escapeHtml(currentProd.name)}</span>
        <span class="fbt-card-price">${formatCurrency(currentProd.price)}</span>
      </div>
    `;

    suggestedProducts.forEach(prod => {
      const imgSug = resolveAssetUrl(prod.image || "assets/images/navy-shirt.png");
      cardsHtml += `
        <div class="fbt-operator">+</div>
        <div class="fbt-card" data-fbt-item="${prod.id}" data-price="${prod.price}">
          <img src="${imgSug}" class="fbt-card-img" alt="${escapeHtml(prod.name)}">
          <label style="display:flex; align-items:center; font-size:0.85rem; color:#fff; cursor:pointer;">
            <input type="checkbox" checked class="fbt-card-checkbox fbt-toggle fbt-item-chk" data-item-id="${prod.id}"> Add suggestion
          </label>
          <span class="fbt-card-title" title="${escapeHtml(prod.name)}">${escapeHtml(prod.name)}</span>
          <span class="fbt-card-price">${formatCurrency(prod.price)}</span>
        </div>
      `;
    });

    cardsHtml += `
      <!-- Bundle Price Summary Box -->
      <div class="fbt-offer-box">
        <div class="fbt-price-row">
          <span class="label">Total Bundle Price:</span>
          <div style="text-align:right;">
            <span class="fbt-regular-price" id="fbt-regular-price" style="text-decoration:line-through; color:var(--gray); margin-right:0.5rem; display:none; font-size:0.9rem;"></span>
            <strong class="fbt-total-price" id="fbt-total">₹0.00</strong>
          </div>
        </div>
        <div class="fbt-discount-badge" id="fbt-discount-badge" style="transition:all 0.2s ease;">🎁 Save 10% with FBT Bundle Deal</div>
        <div id="fbt-status-note" style="font-size:0.8rem; color:#bbb; line-height:1.4;"></div>
        <button class="btn btn-primary" id="fbt-add-btn" style="width:100%; text-transform:uppercase; font-size:0.85rem; font-weight:700;">Add Bundle to Cart</button>
      </div>
    `;

    grid.innerHTML = cardsHtml;

    const checkboxes = grid.querySelectorAll(".fbt-item-chk");
    const totalDisplay = document.getElementById("fbt-total");
    const regularDisplay = document.getElementById("fbt-regular-price");
    const badge = document.getElementById("fbt-discount-badge");
    const statusNote = document.getElementById("fbt-status-note");
    const addBtn = document.getElementById("fbt-add-btn");

    const updateBundleState = () => {
      const checkedCards = Array.from(grid.querySelectorAll(".fbt-card")).filter(
        card => card.querySelector(".fbt-item-chk")?.checked
      );

      let rawSubtotal = 0;
      const selectedProductIds = [];

      checkedCards.forEach(card => {
        const pid = Number(card.dataset.fbtItem);
        const price = Number(card.dataset.price || 0);
        rawSubtotal += price;
        if (!selectedProductIds.includes(pid)) {
          selectedProductIds.push(pid);
        }
      });

      const qualifyingSelected = selectedProductIds.filter(pid => qualifyingIds.includes(pid));
      const isQualified = qualifyingSelected.length >= minDistinct;

      if (isQualified) {
        let qualifyingSubtotal = 0;
        checkedCards.forEach(card => {
          const pid = Number(card.dataset.fbtItem);
          const price = Number(card.dataset.price || 0);
          if (qualifyingSelected.includes(pid)) {
            qualifyingSubtotal += price;
          }
        });

        const discountAmount = Math.round(qualifyingSubtotal * (discountPct / 100.0));
        const finalPrice = Math.max(0, rawSubtotal - discountAmount);

        if (regularDisplay) {
          regularDisplay.textContent = formatCurrency(rawSubtotal);
          regularDisplay.style.display = "inline";
        }
        totalDisplay.textContent = formatCurrency(finalPrice);
        badge.style.display = "block";
        badge.style.background = "rgba(46, 213, 115, 0.15)";
        badge.style.color = "#2ed573";
        badge.textContent = `🎁 Qualified! 10% off bundle savings (-${formatCurrency(discountAmount)})`;
        if (statusNote) {
          statusNote.textContent = `Code BUNDLE10 will apply ${discountPct}% off qualifying items at checkout.`;
          statusNote.style.color = "#2ed573";
        }
        addBtn.textContent = `Add Bundle (${checkedCards.length} items) to Cart`;
      } else {
        if (regularDisplay) {
          regularDisplay.style.display = "none";
        }
        totalDisplay.textContent = formatCurrency(rawSubtotal);
        badge.style.background = "rgba(255, 255, 255, 0.05)";
        badge.style.color = "#aaa";
        badge.textContent = `Select ${minDistinct}+ distinct bundle items to save ${discountPct}%`;
        if (statusNote) {
          statusNote.textContent = `Select at least ${minDistinct} distinct products from this bundle to unlock BUNDLE10.`;
          statusNote.style.color = "#aaa";
        }
        addBtn.textContent = `Add ${checkedCards.length} item${checkedCards.length === 1 ? "" : "s"} to Cart`;
      }

      return { isQualified, selectedCards: checkedCards };
    };

    checkboxes.forEach(chk => {
      chk.addEventListener("change", updateBundleState);
    });

    updateBundleState();

    addBtn.addEventListener("click", async () => {
      const { isQualified, selectedCards } = updateBundleState();
      const totalSelected = selectedCards.length;
      if (totalSelected === 0) {
        showToast("Please select at least one item to add.", "warning");
        return;
      }

      let fullyAdded = 0;
      let partiallyAdded = 0;
      let rejected = 0;

      selectedCards.forEach(card => {
        const itemId = Number(card.dataset.fbtItem);
        const itemObj = allProducts.find(p => Number(p.id) === itemId);
        if (itemObj) {
          const res = addCartItem(itemObj, { size: "M", qty: 1 });
          if (res && res.addedQty === 1) {
            fullyAdded++;
            trackEvent("add_to_cart", { items: [{ item_id: itemObj.id, item_name: itemObj.name, price: itemObj.price, quantity: 1, size: "M" }] });
          } else if (res && res.addedQty > 0) {
            partiallyAdded++;
            trackEvent("add_to_cart", { items: [{ item_id: itemObj.id, item_name: itemObj.name, price: itemObj.price, quantity: res.addedQty, size: "M" }] });
          } else {
            rejected++;
          }
        } else {
          rejected++;
        }
      });

      const totalAdded = fullyAdded + partiallyAdded;

      if (isQualified && fullyAdded === totalSelected && totalSelected > 0) {
        localStorage.setItem("tridentwear-fbt-token", fbtToken);
        localStorage.setItem("tridentwear-applied-coupon", "BUNDLE10");
        notify("cart", `All ${totalSelected} items added as an FBT bundle! 10% discount applied.`, { openDrawer: true });
        showToast(`All ${totalSelected} bundle items added! 10% discount code BUNDLE10 ready at checkout.`, "success");
      } else if (totalAdded > 0) {
        if (!isQualified) {
          if (localStorage.getItem("tridentwear-applied-coupon") === "BUNDLE10") {
            localStorage.removeItem("tridentwear-applied-coupon");
          }
        }
        notify("cart", `${totalAdded} of ${totalSelected} items added to cart.`, { openDrawer: true });
        showToast(`${totalAdded} items added to cart.`, "info");
      } else {
        showToast("Could not add bundle items. Selected items are currently out of stock.", "error");
      }
    });

  } catch (err) {
    console.warn("Failed to load FBT offer:", err);
    section.style.display = "none";
  }
}

function loadTrendingDrops(currentProd, allProducts) {
  const section = document.getElementById("trending-section");
  const grid = document.getElementById("trending-grid");
  if (!section || !grid) return;

  // Filter products that are featured or new
  const trending = allProducts
    .filter(p => String(p.id) !== String(currentProd.id) && p.featured)
    .slice(0, 4);

  if (!trending.length) {
    section.style.display = "none";
    return;
  }

  section.style.display = "block";
  grid.innerHTML = trending.map(productCardMarkup).join("");
  bindProductCardActions(grid, trending);
}

function loadRecentlyViewed(currentId) {
  const section = document.getElementById("recently-viewed-section");
  const grid = document.getElementById("recently-viewed-grid");
  const clearBtn = document.getElementById("clear-recently-viewed");
  if (!section || !grid) return;

  const items = JSON.parse(localStorage.getItem(RV_KEY) || "[]");
  const filtered = items.filter(p => String(p.id) !== String(currentId));
  if (!filtered.length) {
    section.style.display = "none";
    return;
  }

  const toShow = filtered.slice(0, 4);
  grid.innerHTML = toShow.map(p => {
    const prodHref = productUrl(p);
    const img = resolveAssetUrl(p.image || "assets/images/Logo.png");
    return `
      <article class="product-card reveal" style="cursor:pointer;" data-recent-product-link="${escapeHtml(prodHref)}">
        <div class="product-media" style="position:relative; overflow:hidden;">
          <img src="${escapeHtml(img)}" alt="${escapeHtml(p.name)}" loading="lazy" class="product-image">
        </div>
        <div class="product-body">
          <span class="product-type">${escapeHtml(p.category || "T-Shirt")}</span>
          <h3 class="product-name">${escapeHtml(p.name)}</h3>
          <div class="product-footer">
            <strong class="product-price">${formatCurrency(p.price)}</strong>
          </div>
          <a href="${prodHref}" class="btn btn-outline" style="width:100%;text-align:center;display:block;margin-top:0.75rem;padding:0.5rem;font-size:0.85rem;">View Again</a>
        </div>
      </article>`;
  }).join("");

  section.style.display = "block";
  grid.querySelectorAll("[data-recent-product-link]").forEach((card) => {
    card.addEventListener("click", (event) => {
      if (event.target.closest("a")) return;
      window.location.href = card.dataset.recentProductLink;
    });
  });

  clearBtn?.addEventListener("click", () => {
    localStorage.removeItem(RV_KEY);
    section.style.display = "none";
  });
}

function initSizeGuideModal() {
  const link = document.querySelector(".detail-size-guide-link");
  const modal = document.getElementById("size-guide-modal");
  const close = document.getElementById("close-size-guide");
  
  if (!link || !modal || !close) return;
  
  const openModal = (e) => {
    e.preventDefault();
    modal.style.display = "flex";
    document.body.style.overflow = "hidden";
    close.focus();
  };
  
  const closeModal = () => {
    modal.style.display = "none";
    document.body.style.overflow = "";
    link.focus();
  };
  
  link.addEventListener("click", openModal);
  close.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
  
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.style.display === "flex") {
      closeModal();
    }
  });
}

function initPincodeChecker() {
  const btn = document.getElementById("pincode-btn");
  const input = document.getElementById("pincode-input");
  const result = document.getElementById("pincode-result");
  if (!btn || !input || !result) return;

  btn.addEventListener("click", () => {
    const code = input.value.trim();
    if (!/^\d{6}$/.test(code)) {
      result.textContent = "Please enter a valid 6-digit pincode.";
      result.className = "pincode-result-msg is-error";
      result.style.display = "flex";
      return;
    }

    // Mock serviceability ranges
    if (code.startsWith("9")) {
      result.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> Out of service area. Currently we do not ship to this pin code.`;
      result.className = "pincode-result-msg is-error";
      result.style.display = "flex";
    } else {
      const days = 3 + (Number(code) % 3);
      const deliveryDate = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toLocaleDateString("en-IN", {
        weekday: 'long',
        month: 'short',
        day: 'numeric'
      });
      result.innerHTML = `<i class="fa-solid fa-circle-check"></i> Serviceable! Estimated delivery by <strong>${deliveryDate}</strong> (${days} business days). Free Shipping & COD available.`;
      result.className = "pincode-result-msg is-success";
      result.style.display = "flex";
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  await initSite();
  await loadProductDetail();
  initSizeGuideModal();
  initPincodeChecker();
});
