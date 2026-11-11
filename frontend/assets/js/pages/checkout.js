import { STATIC_MODE, post } from "../shared/api.js?v=20260430-v3";
import { clearCart, getCartSubtotal, loadCart } from "../shared/cart.js?v=20260430-v3";
import { formatCurrency, getCurrentUser, initSite, pageUrl, showToast, trackEvent } from "../shared/site.js?v=20260430-v3";

let appliedCoupon = null; // { code, discount_amount, final_total }

// ─── Order summary ────────────────────────────────────────────
function renderSummary(items) {
  const summary = document.querySelector("[data-cart-summary]");
  if (!summary) return;
  const subtotal = getCartSubtotal(items);
  const discountRow = appliedCoupon
    ? `<div class="summary-row" style="color:var(--success);">
         <span>Coupon (${appliedCoupon.code})</span>
         <strong>-${formatCurrency(appliedCoupon.discount_amount)}</strong>
       </div>`
    : "";
  const finalTotal = appliedCoupon ? appliedCoupon.final_total : subtotal;
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
    <div class="summary-row" style="border-top:1px solid #e9ecef;padding-top:0.5rem;margin-top:0.25rem;">
      <span style="font-weight:700;color:var(--gray-dark);">Total</span>
      <strong class="summary-price">${formatCurrency(finalTotal)}</strong>
    </div>
  `;
}

// ─── Coupon ───────────────────────────────────────────────────
function bindCoupon(items) {
  const btn = document.querySelector("[data-coupon-apply]");
  const input = document.querySelector("#coupon-code");
  const msg = document.querySelector("[data-coupon-msg]");
  if (!btn || !input) return;

  btn.addEventListener("click", async () => {
    const code = input.value.trim().toUpperCase();
    if (!code) { showToast("Enter a coupon code.", "error"); return; }
    btn.disabled = true;
    btn.textContent = "Checking…";
    const currentCart = loadCart();
    const payload = {
      code,
      subtotal: getCartSubtotal(currentCart),
      items: currentCart,
    };
    const fbtToken = localStorage.getItem("tridentwear-fbt-token");
    if (fbtToken) {
      payload.fbt_token = fbtToken;
    }
    try {
      const data = await post("/api/v1/coupons/apply", payload);
      appliedCoupon = {
        code: data.code,
        discount_amount: data.discount_amount,
        final_total: data.final_total,
        fbt_token: (data.code === "BUNDLE10" ? fbtToken : null),
        qualifying_product_ids: data.qualifying_product_ids || null,
      };
      localStorage.setItem("tridentwear-applied-coupon", data.code);
      msg.textContent = `${data.discount_pct}% off applied — saving ${formatCurrency(data.discount_amount)}!`;
      msg.style.color = "var(--success)";
      renderSummary(currentCart);
      showToast(`Coupon "${data.code}" applied!`);
    } catch (err) {
      appliedCoupon = null;
      localStorage.removeItem("tridentwear-applied-coupon");
      msg.textContent = err.message || "Invalid coupon.";
      msg.style.color = "var(--danger)";
      renderSummary(currentCart);
    } finally {
      btn.disabled = false;
      btn.textContent = "Apply";
    }
  });
}

// ─── Auto-Apply Stored FBT Coupon ──────────────────────────────
async function autoApplyStoredCoupon(items) {
  const storedCoupon = localStorage.getItem("tridentwear-applied-coupon");
  const storedFbtToken = localStorage.getItem("tridentwear-fbt-token");
  const msg = document.querySelector("[data-coupon-msg]");
  const input = document.querySelector("#coupon-code");

  if (storedCoupon === "BUNDLE10" || storedFbtToken) {
    if (input) input.value = "BUNDLE10";
    if (!items || items.length < 2 || !storedFbtToken) {
      if (msg) {
        msg.textContent = "BUNDLE10 requires at least 2 distinct products from your FBT offer.";
        msg.style.color = "var(--danger)";
      }
      localStorage.removeItem("tridentwear-applied-coupon");
      return;
    }

    try {
      const data = await post("/api/v1/coupons/apply", {
        code: "BUNDLE10",
        subtotal: getCartSubtotal(items),
        fbt_token: storedFbtToken,
        items: items,
      });
      appliedCoupon = {
        code: "BUNDLE10",
        discount_amount: data.discount_amount,
        final_total: data.final_total,
        fbt_token: storedFbtToken,
        qualifying_product_ids: data.qualifying_product_ids || null,
      };
      if (msg) {
        msg.textContent = `10% FBT bundle discount applied — saving ${formatCurrency(data.discount_amount)}!`;
        msg.style.color = "var(--success)";
      }
      renderSummary(items);
    } catch (err) {
      console.warn("FBT auto-qualification check:", err.message);
      appliedCoupon = null;
      localStorage.removeItem("tridentwear-applied-coupon");
      if (msg) {
        msg.textContent = err.message || "Bundle discount disqualified.";
        msg.style.color = "var(--danger)";
      }
      renderSummary(items);
    }
  }
}

// ─── User prefill ─────────────────────────────────────────────
function prefillUser() {
  const user = getCurrentUser();
  if (!user) return;
  const nameField = document.querySelector("#checkout-name");
  const emailField = document.querySelector("#checkout-email");
  if (nameField && !nameField.value) nameField.value = user.name;
  if (emailField && !emailField.value) emailField.value = user.email;
}

// ─── Success screen ───────────────────────────────────────────
function showSuccess(orderId, form, items = [], finalTotal = 0, verifyResult = {}) {
  const waText = encodeURIComponent(`Hello TridentWear! I placed an order ${orderId}.`);
  const waLink = `https://wa.me/919876543210?text=${waText}`;
  
  trackEvent("purchase", {
    transaction_id: orderId,
    value: finalTotal,
    currency: "INR",
    items: items.map(i => ({ item_id: i.id, item_name: i.name, price: i.price, quantity: i.qty }))
  });

  try {
    localStorage.removeItem("tridentwear-fbt-token");
    localStorage.removeItem("tridentwear-applied-coupon");
  } catch (_) {}

  clearCart();
  form.style.display = "none";
  const summaryEl = document.querySelector("[data-cart-summary]");
  if (summaryEl) summaryEl.innerHTML = "";

  const isManualReview = verifyResult?.fulfillment_status === "manual_review_required" || verifyResult?.manual_review_required;
  const statusNotice = isManualReview
    ? `<div class="helper-note warning" style="margin: 1rem 0; padding:0.75rem; border-radius:6px; background:rgba(255,165,2,0.15); color:#ffa502;">
         <strong>Under Priority Review:</strong> Your payment was captured, and order fulfillment is pending verification by our support team.
       </div>`
    : `<p class="order-success-copy">Thank you for your purchase. You'll receive a confirmation email shortly.</p>`;

  showToast(`Order placed! ID: ${orderId}`);
  document.querySelector("[data-order-status]").innerHTML = `
    <div class="order-success-card">
      <div class="order-success-icon">🎉</div>
      <h3 class="order-success-title">Order Placed!</h3>
      <code class="order-success-id">${orderId}</code>
      ${statusNotice}
      <div style="display:flex;gap:0.75rem;flex-wrap:wrap;justify-content:center;margin-top:1rem;">
        <a class="btn btn-primary" href="${pageUrl(`/track?id=${orderId}`)}">Track Order</a>
        <a class="btn btn-secondary" href="${waLink}" target="_blank" rel="noreferrer">WhatsApp Us</a>
        <a class="btn btn-outline" href="${pageUrl("/products")}">Continue Shopping</a>
      </div>
    </div>
  `;
}

// ─── Checkout form + payment routing ─────────────────────────
function bindCheckout(items) {
  const form = document.querySelector("[data-checkout-form]");
  if (!form) return;
  document.querySelectorAll("input[name='payment']").forEach((input) => {
    input.addEventListener("change", () => {
      const btn = document.querySelector("[data-checkout-button]");
      if (btn) btn.textContent = input.value === "cod" ? "Place Order (COD)" : "Pay Online";
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const currentItems = loadCart();
    if (!currentItems.length) { showToast("Your cart is empty.", "error"); return; }

    const method = document.querySelector("input[name='payment']:checked")?.value || "cod";
    const subtotal = getCartSubtotal(currentItems);
    const finalTotal = appliedCoupon
      ? Math.max(0, subtotal - appliedCoupon.discount_amount)
      : subtotal;

    const fbtTokenForOrder = (appliedCoupon && appliedCoupon.code === "BUNDLE10")
      ? (appliedCoupon.fbt_token || localStorage.getItem("tridentwear-fbt-token"))
      : (localStorage.getItem("tridentwear-fbt-token") || null);

    const orderData = {
      items: currentItems,
      subtotal: finalTotal,
      discount_amount: appliedCoupon ? appliedCoupon.discount_amount : 0,
      coupon_code: appliedCoupon ? appliedCoupon.code : null,
      fbt_token: fbtTokenForOrder,
      payment_method: method,
      test_mode: Boolean(form.querySelector("#checkout-test-mode")?.checked),
      customer: {
        name: form.querySelector("#checkout-name").value.trim(),
        email: form.querySelector("#checkout-email").value.trim(),
        phone: form.querySelector("#checkout-phone").value.trim(),
      },
      shipping: {
        address: form.querySelector("#checkout-address").value.trim(),
        city: form.querySelector("#checkout-city").value.trim(),
        postal_code: form.querySelector("#checkout-postal").value.trim(),
        country: form.querySelector("#checkout-country").value.trim() || "India",
        notes: form.querySelector("#checkout-notes").value.trim(),
      },
    };

    const btn = document.querySelector("[data-checkout-button]");
    btn.disabled = true;
    btn.textContent = method === "cod" ? "Placing Order…" : "Opening Payment…";

    try {
      if (method === "cod") {
        const data = await post("/api/v1/payments/cod", {
          ...orderData,
          coupon_code: orderData.coupon_code,
        });
        showSuccess(data.order_id, form, currentItems, finalTotal);

      } else {
        if (STATIC_MODE) {
          const verifyData = await post("/api/v1/payments/verify", {
            razorpay_order_id: `order_${Date.now()}`,
            razorpay_payment_id: `pay_${Date.now()}`,
            razorpay_signature: "static-demo-signature",
            order_data: orderData,
          });
          showSuccess(verifyData.order_id, form, currentItems, finalTotal);
          return;
        }

        // Razorpay online payment
        const rzResp = await post("/api/v1/payments/create-order", {
          amount: Math.round(finalTotal * 100), // paise
          currency: "INR",
          order_data: orderData,
        });

        const options = {
          key: rzResp.key_id,
          amount: rzResp.amount || Math.round(finalTotal * 100),
          currency: rzResp.currency || "INR",
          name: "TridentWear",
          description: "Premium T-Shirt Purchase",
          order_id: rzResp.razorpay_order_id,
          prefill: {
            name: orderData.customer.name,
            email: orderData.customer.email,
            contact: orderData.customer.phone,
          },
          theme: { color: "#6244c5" },
          handler: async (response) => {
            try {
              const verifyData = await post("/api/v1/payments/verify", {
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
                order_data: orderData,
              });
              showSuccess(verifyData.order_id, form, currentItems, finalTotal, verifyData);
            } catch (err) {
              showToast("Payment verification failed: " + err.message, "error");
              btn.disabled = false;
              btn.textContent = "Pay Online";
            }
          },
          modal: {
            ondismiss: () => {
              btn.disabled = false;
              btn.textContent = "Pay Online";
            },
          },
        };

        if (!window.Razorpay) {
          showToast("Razorpay not loaded. Please try again.", "error");
          btn.disabled = false;
          btn.textContent = "Pay Online";
          return;
        }

        new window.Razorpay(options).open();
        return; // Don't re-enable button; handler does it
      }
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      // Only re-enable for COD failures; Razorpay handler manages its own state
      if (method === "cod") {
        btn.disabled = false;
        btn.textContent = "Place Order (COD)";
      }
    }
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  await initSite();
  const items = loadCart();
  trackEvent("begin_checkout", { items: items.map(i => ({ item_id: i.id, item_name: i.name, price: i.price, quantity: i.qty })) });
  renderSummary(items);
  prefillUser();
  bindCoupon(items);
  await autoApplyStoredCoupon(items);
  bindCheckout(items);
});
