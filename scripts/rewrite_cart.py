#!/usr/bin/env python3
"""Rewrite cart.js from scratch with all fixes included."""

content = '''import { post, resolveAssetUrl } from "../shared/api.js?v=9";
import { getCartSubtotal, loadCart, removeCartItem, updateCartItemQuantity } from "../shared/cart.js?v=9";
import { createEmptyMarkup, endGlobalLoader, escapeHtml, formatCurrency, initSite, showToast, startGlobalLoader } from "../shared/site.js?v=9";

let appliedCartCoupon = null;

function renderSummary(items) {
  const summary = document.querySelector("[data-cart-summary]");
  if (!summary) return;
  const subtotal = getCartSubtotal(items);
  const discountRow = appliedCartCoupon
    ? `<div class="summary-row" style="color:var(--success,#22c55e);"><span>Coupon (${appliedCartCoupon.code})</span><strong>-${formatCurrency(appliedCartCoupon.discount_amount)}</strong></div>`
    : "";
  const finalTotal = appliedCartCoupon ? appliedCartCoupon.final_total : subtotal;
  summary.innerHTML = `
    <div class="summary-row">
      <span>Subtotal</span>
      <strong class="summary-price">${formatCurrency(subtotal)}</strong>
    </div>
    <div class="summary-row">
      <span>Items</span>
      <strong>${items.length}</strong>
    </div>
    ${discountRow}
    <div class="summary-row" style="border-top:1px solid rgba(255,255,255,.1);padding-top:0.5rem;margin-top:0.25rem;">
      <span style="font-weight:700;">Total</span>
      <strong class="summary-price">${formatCurrency(finalTotal)}</strong>
    </div>
  `;
}

function bindCartActions() {
  document.querySelectorAll("[data-qty-change]").forEach((button) => {
    button.addEventListener("click", () => {
      const { id, size, delta } = button.dataset;
      const item = loadCart().find((entry) => String(entry.id) === id && entry.size === size);
      if (!item) {
        return;
      }
      updateCartItemQuantity(Number(id), size, Number(item.qty) + Number(delta));
      renderCart();
    });
  });

  document.querySelectorAll("[data-remove-item]").forEach((button) => {
    button.addEventListener("click", () => {
      removeCartItem(Number(button.dataset.id), button.dataset.size);
      renderCart();
    });
  });
}

function renderCart() {
  const items = loadCart();
  const list = document.querySelector("[data-cart-list]");
  const checkoutBtn = document.querySelector("a[href='/checkout']");

  if (!items.length) {
    if (list) list.innerHTML = createEmptyMarkup("Your cart is empty", "Add a few premium pieces and come back here.");
    if (checkoutBtn) checkoutBtn.style.pointerEvents = "none";
    if (checkoutBtn) checkoutBtn.classList.add("disabled");
    renderSummary(items);
    return;
  }

  if (checkoutBtn) checkoutBtn.style.pointerEvents = "auto";
  if (checkoutBtn) checkoutBtn.classList.remove("disabled");

  if (list) {
    list.innerHTML = items
      .map(
        (item) => `
          <article class="cart-item">
            <div class="cart-item-media">
              <img src="${resolveAssetUrl(item.image)}" alt="${escapeHtml(item.name)}" loading="lazy" decoding="async">
            </div>
            <div>
              <div class="cart-item-title-row">
                <div>
                  <strong>${escapeHtml(item.name)}</strong>
                  <div class="label">Size ${escapeHtml(item.size)}</div>
                </div>
                <strong class="cart-item-price">${formatCurrency(item.price)}</strong>
              </div>
              <div class="cart-row-actions">
                <div class="quantity-control">
                  <button class="qty-button" type="button" data-qty-change data-id="${item.id}" data-size="${escapeHtml(item.size)}" data-delta="-1" aria-label="Decrease quantity">-</button>
                  <span>${item.qty}</span>
                  <button class="qty-button" type="button" data-qty-change data-id="${item.id}" data-size="${escapeHtml(item.size)}" data-delta="1" aria-label="Increase quantity">+</button>
                </div>
                <button class="btn btn-outline" type="button" data-remove-item data-id="${item.id}" data-size="${escapeHtml(item.size)}">Remove</button>
              </div>
            </div>
          </article>
        `,
      )
      .join("");
  }

  renderSummary(items);
  bindCartActions();
}

function bindCartCoupon() {
  const btn = document.getElementById("cart-coupon-apply");
  const input = document.getElementById("cart-coupon-code");
  const msg = document.getElementById("cart-coupon-msg");
  if (!btn || !input) return;
  btn.addEventListener("click", async () => {
    const code = input.value.trim();
    if (!code) { showToast("Enter a coupon code.", "error"); return; }
    btn.disabled = true;
    btn.textContent = "Checking\u2026";
    try {
      const data = await post("/api/coupons/apply", {
        code,
        subtotal: getCartSubtotal(loadCart()),
      });
      appliedCartCoupon = { code: data.code, discount_amount: data.discount_amount, final_total: data.final_total };
      if (msg) {
        msg.textContent = `${data.discount_pct}% off applied \u2014 saving ${formatCurrency(data.discount_amount)}!`;
        msg.style.color = "var(--success, #22c55e)";
      }
      renderSummary(loadCart());
      showToast(`Coupon "${data.code}" applied!`, "success");
    } catch (err) {
      appliedCartCoupon = null;
      if (msg) {
        msg.textContent = err.message;
        msg.style.color = "var(--danger, #ef4444)";
      }
      renderSummary(loadCart());
    } finally {
      btn.disabled = false;
      btn.textContent = "Apply";
    }
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  await initSite();
  const list = document.querySelector("[data-cart-list]");
  if (list) {
    list.innerHTML = `
      <div class="skeleton" style="height:8rem;margin-bottom:1rem;border-radius:var(--radius);"></div>
      <div class="skeleton" style="height:8rem;margin-bottom:1rem;border-radius:var(--radius);"></div>
      <div class="skeleton" style="height:8rem;margin-bottom:1rem;border-radius:var(--radius);"></div>
    `;
  }
  
  startGlobalLoader();
  setTimeout(() => {
    renderCart();
    bindCartCoupon();
    endGlobalLoader();
    if (list) list.classList.add("fade-in");
  }, 500);
});
'''

# Use template literal substitution to avoid Python format string issues
# The content above uses JavaScript template literals - we need to write it as-is
with open('frontend/assets/js/pages/cart.js', 'w', encoding='utf-8', newline='\r\n') as f:
    f.write(content)
print('cart.js rewritten successfully')
