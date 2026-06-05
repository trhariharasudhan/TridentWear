import { STATIC_MODE, post } from "../shared/api.js?v=20260430-v3";
import { clearCart, getCartSubtotal, loadCart } from "../shared/cart.js?v=20260430-v3";
import { formatCurrency, getCurrentUser, initSite, pageUrl, showToast } from "../shared/site.js?v=20260430-v3";

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
    const code = input.value.trim();
    if (!code) { showToast("Enter a coupon code.", "error"); return; }
    btn.disabled = true;
    btn.textContent = "Checking…";
    try {
      const data = await post("/api/v1/coupons/apply", {
        code,
        subtotal: getCartSubtotal(items),
      });
      appliedCoupon = { code: data.code, discount_amount: data.discount_amount, final_total: data.final_total };
      msg.textContent = `${data.discount_pct}% off applied — saving ${formatCurrency(data.discount_amount)}!`;
      msg.style.color = "var(--success)";
      renderSummary(items);
      showToast(`Coupon "${data.code}" applied!`);
    } catch (err) {
      appliedCoupon = null;
      msg.textContent = err.message;
      msg.style.color = "var(--danger)";
      renderSummary(items);
    } finally {
      btn.disabled = false;
      btn.textContent = "Apply";
    }
  });
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
function showSuccess(orderId, form) {
  const waText = encodeURIComponent(`Hello TridentWear! I placed an order ${orderId}.`);
  const waLink = `https://wa.me/919876543210?text=${waText}`;
  clearCart();
  form.style.display = "none";
  const summaryEl = document.querySelector("[data-cart-summary]");
  if (summaryEl) summaryEl.innerHTML = "";
  showToast(`Order placed! ID: ${orderId}`);
  document.querySelector("[data-order-status]").innerHTML = `
    <div class="order-success-card">
      <div class="order-success-icon">🎉</div>
      <h3 class="order-success-title">Order Placed!</h3>
      <code class="order-success-id">${orderId}</code>
      <p class="order-success-copy">Thank you for your purchase. You'll receive a confirmation email shortly.</p>
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
    const finalTotal = appliedCoupon ? appliedCoupon.final_total : subtotal;

    const orderData = {
      items: currentItems,
      subtotal: finalTotal,
      discount_amount: appliedCoupon ? appliedCoupon.discount_amount : 0,
      coupon_code: appliedCoupon ? appliedCoupon.code : null,
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
        showSuccess(data.order_id, form);

      } else {
        if (STATIC_MODE) {
          const verifyData = await post("/api/v1/payments/verify", {
            razorpay_order_id: `order_${Date.now()}`,
            razorpay_payment_id: `pay_${Date.now()}`,
            razorpay_signature: "static-demo-signature",
            order_data: orderData,
          });
          showSuccess(verifyData.order_id, form);
          return;
        }

        // Razorpay online payment
        const rzResp = await post("/api/v1/payments/create-order", {
          amount: Math.round(finalTotal * 100), // paise
          currency: "INR",
        });

        const options = {
          key: rzResp.key_id,
          amount: Math.round(finalTotal * 100),
          currency: "INR",
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
              showSuccess(verifyData.order_id, form);
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
  renderSummary(items);
  prefillUser();
  bindCoupon(items);
  bindCheckout(items);
});
