import { del, get, post, postForm, put, putForm, resolveAssetUrl } from "../shared/api.js?v=20260430-v3";
import { normalizeProduct } from "../shared/catalog.js?v=20260430-v3";
import { createLoaderMarkup, escapeHtml, formatCurrency, getCurrentUser, initSite, pageUrl, showToast } from "../shared/site.js?v=20260430-v3";

let products = [];
let editingProductId = null;
let orders = [];
let analytics = null;
let reviews = [];
let reviewFilter = "";
const ORDER_STATUSES = ["placed", "confirmed", "packed", "shipped", "delivered", "cancelled"];
const PAYMENT_STATUSES = ["pending", "cod_pending", "paid", "failed", "refunded"];

function fields() {
  return {
    name: document.querySelector("#admin-name"),
    category: document.querySelector("#admin-category"),
    price: document.querySelector("#admin-price"),
    description: document.querySelector("#admin-description"),
    tag: document.querySelector("#admin-tag"),
    sizes: document.querySelector("#admin-sizes"),
    stock: document.querySelector("#admin-stock"),
    fabric: document.querySelector("#admin-fabric"),
    gsm: document.querySelector("#admin-gsm"),
    fitType: document.querySelector("#admin-fit-type"),
    neckType: document.querySelector("#admin-neck-type"),
    printMethod: document.querySelector("#admin-print-method"),
    featured: document.querySelector("#admin-featured"),
    image: document.querySelector("#admin-image"),
  };
}

function setFormState(product = null) {
  const f = fields();
  const title = document.querySelector("[data-admin-form-title]");
  const submit = document.querySelector("[data-admin-submit]");
  const cancel = document.querySelector("[data-admin-cancel]");
  const preview = document.querySelector("[data-preview-image]");

  if (!product) {
    editingProductId = null;
    title.textContent = "Add New Product";
    submit.textContent = "Save Product";
    cancel.hidden = true;
    f.name.value = "";
    f.category.value = "tshirt";
    f.price.value = "";
    f.description.value = "";
    f.tag.value = "";
    f.sizes.value = "S, M, L, XL";
    f.stock.value = "100";
    f.fabric.value = "100% Cotton";
    f.gsm.value = "150";
    f.fitType.value = "Unisex";
    f.neckType.value = "Round Neck";
    f.printMethod.value = "DTG, Embroidery";
    f.featured.checked = false;
    f.image.value = "";
    preview.hidden = true;
    preview.src = "";
    return;
  }

  editingProductId = product.id;
  title.textContent = `Edit ${product.name}`;
  submit.textContent = "Update Product";
  cancel.hidden = false;
  f.name.value = product.name;
  f.category.value = product.category;
  f.price.value = product.price;
  f.description.value = product.description;
  f.tag.value = product.tag || "";
  f.sizes.value = product.sizes.join(", ");
  f.stock.value = product.stock;
  f.fabric.value = product.fabric || product.material || "100% Cotton";
  f.gsm.value = product.gsm || 150;
  f.fitType.value = product.fit_type || "Unisex";
  f.neckType.value = product.neck_type || "Round Neck";
  f.printMethod.value = (product.print_method || ["DTG", "Embroidery"]).join(", ");
  f.featured.checked = Boolean(product.featured);
  f.image.value = "";
  preview.hidden = false;
    preview.src = resolveAssetUrl(product.image);
}

function bindPreview() {
  const input = document.querySelector("#admin-image");
  const preview = document.querySelector("[data-preview-image]");

  input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    preview.hidden = false;
    preview.src = URL.createObjectURL(file);
  });
}

function renderSummary() {
  const lowStock = products.filter((product) => Number(product.stock || 0) <= 10).length;
  document.querySelector("[data-summary-total]").textContent = String(products.length);
  document.querySelector("[data-summary-low-stock]").textContent = String(lowStock);
  document.querySelector("[data-summary-featured]").textContent = String(products.filter((product) => product.featured).length);
  const orderEl = document.querySelector("[data-summary-orders]");
  if (orderEl) orderEl.textContent = String(orders.length);
}

function renderAdminOverview() {
  const pending = orders.filter((order) => ["placed", "confirmed", "packed", "pending", "processing"].includes(String(order.status || "").toLowerCase())).length;
  const shipped = orders.filter((order) => ["shipped", "delivered"].includes(String(order.status || "").toLowerCase())).length;
  const revenue = analytics?.total_revenue ?? orders.reduce((sum, order) => sum + Number(order.subtotal || 0), 0);
  const pendingEl = document.querySelector("[data-admin-orders-pending]");
  const shippedEl = document.querySelector("[data-admin-orders-shipped]");
  const revenueEl = document.querySelector("[data-admin-revenue]");
  const analyticsEl = document.querySelector("[data-admin-analytics]");
  if (pendingEl) pendingEl.textContent = String(pending);
  if (shippedEl) shippedEl.textContent = String(shipped);
  if (revenueEl) revenueEl.textContent = formatCurrency(revenue);
  if (analyticsEl) {
    const top = analytics?.top_products?.[0];
    analyticsEl.innerHTML = top
      ? `<strong>${top.name}</strong><span>${top.sold} units sold. Add conversion and cohort charts when traffic analytics are connected.</span>`
      : `<strong>Waiting for order volume</strong><span>Conversion, returning customers, and drop velocity will appear here as data grows.</span>`;
  }
}

function statusBadge(value, type = "status") {
  const text = String(value || "pending").replace(/_/g, " ");
  return `<span class="admin-status-badge ${type}-${String(value || "pending").toLowerCase()}">${escapeHtml(text)}</span>`;
}

function renderOrders() {
  const list = document.querySelector("[data-admin-order-list]");
  if (!list) return;
  if (!orders.length) {
    list.innerHTML = `<div class="helper-note info">No orders yet. Test checkout will appear here when submitted.</div>`;
    return;
  }

  list.innerHTML = orders.map((order) => {
    const status = String(order.status || "placed").toLowerCase();
    const paymentStatus = String(order.payment_status || (order.method === "COD" ? "cod_pending" : "pending")).toLowerCase();
    return `
      <article class="admin-order-card" data-order-id="${escapeHtml(order.order_id)}">
        <div class="admin-order-head">
          <div>
            <strong>${escapeHtml(order.order_id || "Order")}</strong>
            <span>${escapeHtml(order.customer?.name || "Customer")} - ${formatCurrency(order.subtotal || order.total || 0)}</span>
          </div>
          <div class="admin-badge-row">
            ${order.test_mode ? `<span class="admin-test-badge">TEST</span>` : ""}
            ${statusBadge(status)}
            ${statusBadge(paymentStatus, "payment")}
          </div>
        </div>
        <div class="admin-order-fields">
          <label>Status
            <select class="status-select" data-order-status>
              ${ORDER_STATUSES.map((item) => `<option value="${item}" ${item === status ? "selected" : ""}>${item}</option>`).join("")}
            </select>
          </label>
          <label>Payment
            <select class="status-select" data-payment-status>
              ${PAYMENT_STATUSES.map((item) => `<option value="${item}" ${item === paymentStatus ? "selected" : ""}>${item.replace(/_/g, " ")}</option>`).join("")}
            </select>
          </label>
          <label>Courier <input class="field compact-field" data-courier value="${escapeHtml(order.courier || "")}" placeholder="Delhivery"></label>
          <label>Tracking <input class="field compact-field" data-tracking value="${escapeHtml(order.tracking_id || "")}" placeholder="AWB / tracking ID"></label>
          <label>ETA <input class="field compact-field" data-eta value="${escapeHtml(order.estimated_delivery || "")}" placeholder="YYYY-MM-DD"></label>
        </div>
        <div class="admin-actions">
          <button class="btn btn-outline" type="button" data-save-order="${escapeHtml(order.order_id)}">Save Order</button>
        </div>
      </article>
    `;
  }).join("");

  list.querySelectorAll("[data-save-order]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest("[data-order-id]");
      const orderId = button.dataset.saveOrder;
      button.disabled = true;
      try {
        await put(`/api/v1/admin/orders/${orderId}`, {
          status: card.querySelector("[data-order-status]").value,
          payment_status: card.querySelector("[data-payment-status]").value,
          courier: card.querySelector("[data-courier]").value,
          tracking_id: card.querySelector("[data-tracking]").value,
          estimated_delivery: card.querySelector("[data-eta]").value,
        });
        showToast("Order updated.");
        await loadAdminMetrics();
      } catch (error) {
        showToast(error.message, "error");
      } finally {
        button.disabled = false;
      }
    });
  });
}

function renderReviews(payload = {}) {
  const list = document.querySelector("[data-admin-review-list]");
  if (!list) return;
  reviews = payload.reviews || [];
  const counts = payload.counts || {};
  document.querySelectorAll("[data-review-status]").forEach((button) => {
    const status = button.dataset.reviewStatus;
    const suffix = status && counts[status] != null ? ` (${counts[status]})` : "";
    button.textContent = `${status ? status.charAt(0).toUpperCase() + status.slice(1) : "All"}${suffix}`;
    button.classList.toggle("is-active", status === reviewFilter);
  });
  if (!reviews.length) {
    list.innerHTML = `<div class="helper-note info">No reviews in this view.</div>`;
    return;
  }
  list.innerHTML = reviews.map((review) => `
    <article class="admin-review-card" data-review-id="${review.id}">
      <div class="admin-order-head">
        <div>
          <strong>${"★".repeat(Number(review.rating || 0))}${"☆".repeat(5 - Number(review.rating || 0))}</strong>
          <span>${escapeHtml(review.user_name || "Customer")} on product #${escapeHtml(review.product_id)}</span>
        </div>
        ${statusBadge(String(review.status || "pending").replace("_moderation", ""))}
      </div>
      <p class="section-copy">${escapeHtml(review.review || "")}</p>
      <textarea class="textarea admin-notes-field" data-review-notes placeholder="Moderation notes">${escapeHtml(review.moderation_notes || "")}</textarea>
      <div class="admin-actions">
        <button class="btn btn-outline" type="button" data-review-action="approved">Approve</button>
        <button class="btn btn-outline" type="button" data-review-action="rejected">Reject</button>
        <button class="btn btn-danger" type="button" data-review-delete>Delete</button>
      </div>
    </article>
  `).join("");

  list.querySelectorAll("[data-review-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest("[data-review-id]");
      try {
        await put(`/api/v1/admin/reviews/${card.dataset.reviewId}`, {
          status: button.dataset.reviewAction,
          moderation_notes: card.querySelector("[data-review-notes]").value,
        });
        showToast(`Review ${button.dataset.reviewAction}.`);
        await loadReviews();
      } catch (error) {
        showToast(error.message, "error");
      }
    });
  });

  list.querySelectorAll("[data-review-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest("[data-review-id]");
      if (!window.confirm("Delete this review?")) return;
      try {
        await del(`/api/v1/admin/reviews/${card.dataset.reviewId}`);
        showToast("Review deleted.");
        await loadReviews();
      } catch (error) {
        showToast(error.message, "error");
      }
    });
  });
}

function renderProducts() {
  const list = document.querySelector("[data-admin-product-list]");
  if (!list) return;
  if (!products.length) {
    list.innerHTML = `<div class="helper-note warning">No products found yet. Use the form to add the first drop.</div>`;
    return;
  }

  list.innerHTML = products
    .map(
      (product) => `
        <article class="admin-product-card">
          <div class="admin-product-top">
            <div>
              <strong>${escapeHtml(product.name)}</strong>
              <div class="section-copy">T-Shirt - ${formatCurrency(product.price)}</div>
              <div class="section-copy">${(product.card_tags || []).map(t => escapeHtml(t)).join(" / ")}</div>
              <div class="admin-stock-line ${Number(product.stock || 0) <= 10 ? "is-low" : "}">
                <span>${escapeHtml(String(product.stock))} stock</span>
                <span>${product.featured ? "Featured" : "Standard"}</span>
              </div>
            </div>
            <img class="admin-thumb" src="${resolveAssetUrl(product.image)}" alt="${escapeHtml(product.name)}">
          </div>
          <p class="section-copy">${escapeHtml(product.description)}</p>
          <div class="admin-actions">
            <button class="btn btn-outline" type="button" data-edit-product="${product.id}">Edit</button>
            <button class="btn btn-danger" type="button" data-delete-product="${product.id}">Delete</button>
          </div>
        </article>
      `,
    )
    .join("");

  list.querySelectorAll("[data-edit-product]").forEach((button) => {
    button.addEventListener("click", () => {
      const product = products.find((entry) => entry.id === Number(button.dataset.editProduct));
      if (product) {
        setFormState(product);
      }
    });
  });

  list.querySelectorAll("[data-delete-product]").forEach((button) => {
    button.addEventListener("click", async () => {
      const product = products.find((entry) => entry.id === Number(button.dataset.deleteProduct));
      if (!product || !window.confirm(`Delete ${product.name}?`)) {
        return;
      }

      try {
        await del(`/api/v1/admin/products/${product.id}`);
        showToast(`${product.name} deleted.`);
        await loadProducts();
      } catch (error) {
        showToast(error.message, "error");
      }
    });
  });
}

function populateCategoryDropdown() {
  const select = document.getElementById("admin-category");
  if (!select) return;

  const uniqueCategories = new Set(["tshirt", "shirt"]);
  products.forEach((p) => {
    if (p.category) uniqueCategories.add(p.category);
  });

  const currentValue = select.value || "tshirt";

  select.innerHTML = Array.from(uniqueCategories)
    .map((cat) => {
      const label = cat === "tshirt" ? "T-Shirt" : cat === "shirt" ? "Shirt" : cat.charAt(0).toUpperCase() + cat.slice(1);
      return `<option value="${escapeHtml(cat)}">${escapeHtml(label)}</option>`;
    })
    .join("");

  if (Array.from(uniqueCategories).includes(currentValue)) {
    select.value = currentValue;
  }
}

async function updateSupportBadge() {
  const badge = document.querySelector("[data-admin-chat-badge]");
  if (!badge) return;
  try {
    const threads = await get("/api/v1/admin/chat");
    let pendingCount = 0;
    Object.keys(threads).forEach((tid) => {
      const messages = threads[tid];
      if (messages && messages.length) {
        const lastMsg = messages[messages.length - 1];
        if (lastMsg.role === "user" && !lastMsg.read) {
          pendingCount++;
        }
      }
    });

    if (pendingCount > 0) {
      badge.textContent = String(pendingCount);
      badge.style.display = "inline-block";
      badge.style.background = "var(--primary, #6244c5)";
    } else {
      const totalThreads = Object.keys(threads).length;
      if (totalThreads > 0) {
        badge.textContent = String(totalThreads);
        badge.style.display = "inline-block";
        badge.style.background = "var(--gray, #6c757d)";
      } else {
        badge.style.display = "none";
      }
    }
  } catch (err) {
    console.error("Failed to load chat stats for badge:", err);
  }
}

async function loadProducts() {
  const list = document.querySelector("[data-admin-product-list]");
  list.innerHTML = createLoaderMarkup("Loading product manager...");
  const data = await get("/api/v1/products");
  products = (Array.isArray(data) ? data : data.products || []).map(normalizeProduct);
  populateCategoryDropdown();
  renderSummary();
  renderProducts();
}

async function loadAdminMetrics() {
  try {
    orders = await get("/api/v1/admin/orders");
  } catch (_) {
    orders = [];
  }
  try {
    analytics = await get("/api/v1/admin/analytics");
  } catch (_) {
    analytics = null;
  }
  renderSummary();
  renderAdminOverview();
  renderOrders();
}

async function loadReviews() {
  const query = reviewFilter ? `?status=${reviewFilter}` : "";
  const data = await get(`/api/v1/admin/reviews${query}`);
  renderReviews(data || {});
}

function bindReviewTabs() {
  document.querySelectorAll("[data-review-status]").forEach((button) => {
    button.addEventListener("click", async () => {
      reviewFilter = button.dataset.reviewStatus || "";
      await loadReviews();
    });
  });
}

function buildFormData() {
  const f = fields();
  const formData = new FormData();
  formData.append("name", f.name.value.trim());
  formData.append("category", f.category.value);
  formData.append("price", f.price.value.trim());
  formData.append("description", f.description.value.trim());
  formData.append("tag", f.tag.value.trim());
  formData.append("sizes", f.sizes.value.trim());
  formData.append("stock", f.stock.value.trim());
  formData.append("fabric", f.fabric.value.trim());
  formData.append("gsm", f.gsm.value.trim());
  formData.append("fit_type", f.fitType.value.trim());
  formData.append("neck_type", f.neckType.value.trim());
  formData.append("print_method", f.printMethod.value.trim());
  formData.append("wash_care_label", "true");
  formData.append("featured", f.featured.checked ? "true" : "false");
  if (f.image.files?.[0]) {
    formData.append("image", f.image.files[0]);
  }
  return formData;
}

function bindForm() {
  const form = document.querySelector("[data-admin-form]");
  const cancel = document.querySelector("[data-admin-cancel]");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = document.querySelector("[data-admin-submit]");
    submit.disabled = true;
    submit.textContent = editingProductId ? "Updating..." : "Saving...";

    try {
      if (editingProductId) {
        await putForm(`/api/v1/admin/products/${editingProductId}`, buildFormData());
        showToast("Product updated.");
      } else {
        await postForm("/api/v1/admin/products", buildFormData());
        showToast("Product created.");
      }
      setFormState();
      await loadProducts();
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      submit.disabled = false;
      submit.textContent = editingProductId ? "Update Product" : "Save Product";
    }
  });

  cancel.addEventListener("click", () => setFormState());
}

// ─── COUPON MANAGER STATE & CRUD ───────────────────────────────────────
let coupons = [];
let editingCouponCode = null;

function couponFields() {
  return {
    originalCode: document.querySelector("#coupon-original-code"),
    code: document.querySelector("#coupon-code-field"),
    discount: document.querySelector("#coupon-discount-field"),
    expiry: document.querySelector("#coupon-expiry-field"),
    limit: document.querySelector("#coupon-limit-field"),
    active: document.querySelector("#coupon-active-field"),
  };
}

function setCouponFormState(coupon = null) {
  const f = couponFields();
  const title = document.querySelector("[data-admin-coupon-form-title]");
  const submit = document.querySelector("[data-admin-coupon-submit]");
  const cancel = document.querySelector("[data-admin-coupon-cancel]");
  
  if (!coupon) {
    editingCouponCode = null;
    if (title) title.textContent = "Add Promo Coupon";
    if (submit) submit.textContent = "Save Coupon";
    if (cancel) cancel.hidden = true;
    if (f.originalCode) f.originalCode.value = "";
    if (f.code) { f.code.value = ""; f.code.disabled = false; }
    if (f.discount) f.discount.value = "";
    if (f.expiry) f.expiry.value = "";
    if (f.limit) f.limit.value = "1000";
    if (f.active) f.active.checked = true;
    return;
  }
  
  editingCouponCode = coupon.code;
  if (title) title.textContent = `Edit Coupon ${coupon.code}`;
  if (submit) submit.textContent = "Update Coupon";
  if (cancel) cancel.hidden = false;
  if (f.originalCode) f.originalCode.value = coupon.code;
  if (f.code) { f.code.value = coupon.code; f.code.disabled = true; }
  if (f.discount) f.discount.value = coupon.discount_pct;
  if (f.expiry) {
    try {
      f.expiry.value = coupon.expires_at.split("T")[0];
    } catch (_) {
      f.expiry.value = coupon.expires_at || "";
    }
  }
  if (f.limit) f.limit.value = coupon.usage_limit;
  if (f.active) f.active.checked = Boolean(coupon.is_active);
}

function renderCoupons() {
  const list = document.querySelector("[data-admin-coupon-list]");
  if (!list) return;
  if (!coupons.length) {
    list.innerHTML = `<div class="helper-note info">No coupons found. Add one above.</div>`;
    return;
  }
  
  list.innerHTML = coupons.map(c => {
    const limit = c.usage_limit;
    const count = c.usage_count;
    const discount = c.discount_pct;
    const activeStr = c.is_active ? "Active" : "Disabled";
    const statusClass = c.is_active ? "payment-paid" : "payment-failed";
    
    return `
      <article class="admin-product-card" data-coupon-code="${escapeHtml(c.code)}">
        <div class="admin-product-top">
          <div>
            <strong>${escapeHtml(c.code)}</strong>
            <div class="section-copy" style="margin-top:0.25rem;">Discount: <strong>${escapeHtml(String(discount))}%</strong></div>
            <div class="section-copy">Expires: <strong>${escapeHtml(String(c.expires_at))}</strong></div>
            <div class="admin-stock-line ${count >= limit ? 'is-low' : ''}" style="margin-top:0.5rem;">
              <span>Usage: ${escapeHtml(String(count))} / ${escapeHtml(String(limit))}</span>
              <span class="admin-status-badge ${statusClass}">${activeStr}</span>
            </div>
          </div>
        </div>
        <div class="admin-actions" style="margin-top: 1rem;">
          <button class="btn btn-outline" type="button" data-edit-coupon="${escapeHtml(c.code)}">Edit</button>
          <button class="btn btn-outline" type="button" data-toggle-coupon="${escapeHtml(c.code)}" data-active="${c.is_active}">${c.is_active ? 'Disable' : 'Enable'}</button>
          <button class="btn btn-danger" type="button" data-delete-coupon="${escapeHtml(c.code)}">Delete</button>
        </div>
      </article>
    `;
  }).join("");
  
  list.querySelectorAll("[data-edit-coupon]").forEach(btn => {
    btn.addEventListener("click", () => {
      const code = btn.dataset.editCoupon;
      const coupon = coupons.find(c => c.code === code);
      if (coupon) setCouponFormState(coupon);
    });
  });
  
  list.querySelectorAll("[data-toggle-coupon]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const code = btn.dataset.toggleCoupon;
      const isCurrentlyActive = btn.dataset.active === "true";
      btn.disabled = true;
      try {
        const payload = { is_active: !isCurrentlyActive };
        await put(`/api/v1/admin/coupons/${code}`, payload);
        showToast(`Coupon "${code}" ${!isCurrentlyActive ? 'enabled' : 'disabled'}.`);
        await loadCoupons();
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    });
  });
  
  list.querySelectorAll("[data-delete-coupon]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const code = btn.dataset.deleteCoupon;
      if (!window.confirm(`Delete coupon "${code}"?`)) return;
      btn.disabled = true;
      try {
        await del(`/api/v1/admin/coupons/${code}`);
        showToast(`Coupon "${code}" deleted.`);
        setCouponFormState();
        await loadCoupons();
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    });
  });
}

async function loadCoupons() {
  const list = document.querySelector("[data-admin-coupon-list]");
  if (!list) return;
  try {
    const data = await get("/api/v1/admin/coupons");
    coupons = Array.isArray(data) ? data : [];
    renderCoupons();
  } catch (err) {
    console.error("Failed to load coupons:", err);
    list.innerHTML = `<div class="helper-note danger">Failed to load coupons.</div>`;
  }
}

function bindCouponForm() {
  const form = document.querySelector("[data-admin-coupon-form]");
  if (!form) return;
  const cancel = document.querySelector("[data-admin-coupon-cancel]");
  
  cancel?.addEventListener("click", () => setCouponFormState());
  
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const submit = document.querySelector("[data-admin-coupon-submit]");
    if (!submit) return;
    
    submit.disabled = true;
    submit.textContent = editingCouponCode ? "Updating..." : "Saving...";
    
    const f = couponFields();
    const payload = {
      code: f.code.value.trim().toUpperCase(),
      discount_pct: Number(f.discount.value),
      expires_at: f.expiry.value,
      usage_limit: Number(f.limit.value),
      is_active: f.active.checked,
    };
    
    try {
      if (editingCouponCode) {
        await put(`/api/v1/admin/coupons/${editingCouponCode}`, {
          discount_pct: payload.discount_pct,
          expires_at: payload.expires_at,
          usage_limit: payload.usage_limit,
          is_active: payload.is_active,
        });
        showToast(`Coupon "${editingCouponCode}" updated.`);
      } else {
        await post("/api/v1/admin/coupons", payload);
        showToast(`Coupon "${payload.code}" created.`);
      }
      setCouponFormState();
      await loadCoupons();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      submit.disabled = false;
      submit.textContent = editingCouponCode ? "Update Coupon" : "Save Coupon";
    }
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  await initSite();
  const user = getCurrentUser();
  if (!user || user.role !== "admin") {
    window.location.href = pageUrl(`/login?next=${encodeURIComponent("/admin")}`);
    return;
  }

  bindForm();
  bindPreview();
  bindReviewTabs();
  setFormState();
  
  bindCouponForm();
  setCouponFormState();

  try {
    await loadProducts();
    await loadAdminMetrics();
    await loadReviews();
    await updateSupportBadge();
    await loadCoupons();
  } catch (error) {
    const adminList = document.querySelector("[data-admin-product-list]");
    if (adminList) {
      adminList.innerHTML = `<div class="helper-note danger">${escapeHtml(error.message || "Failed to load admin data.")}</div>`;
    }
  }
});
