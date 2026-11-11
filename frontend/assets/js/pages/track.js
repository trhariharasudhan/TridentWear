import { get } from "../shared/api.js?v=20260430-v3";
import { initSite, startProgress, endProgress, showToast } from "../shared/site.js?v=20260430-v3";

async function trackOrder() {
  const form = document.querySelector("[data-track-form]");
  const input = document.getElementById("track-order-id");
  const resultDiv = document.getElementById("track-result");
  
  if (!form || !input || !resultDiv) return;

  // Check URL for orderId
  const urlParams = new URLSearchParams(window.location.search);
  const orderId = urlParams.get("id");
  if (orderId) {
    input.value = orderId;
    triggerTracking(orderId);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = input.value.trim();
    const emailInput = document.getElementById("track-email");
    const email = emailInput ? emailInput.value.trim() : "";
    if (id) triggerTracking(id, email);
  });
}

async function triggerTracking(orderId, email) {
  const resultDiv = document.getElementById("track-result");
  
  try {
    startProgress();
    const query = email ? `?email=${encodeURIComponent(email)}` : "";
    const data = await get(`/api/v1/orders/${orderId}/tracking${query}`);
    
    resultDiv.style.display = "block";
    updateTrackingUI(data);
    
    resultDiv.scrollIntoView({ behavior: 'smooth' });
  } catch (error) {
    showToast(error.message || "Order not found", "error");
    resultDiv.style.display = "none";
  } finally {
    endProgress();
  }
}

function updateTrackingUI(data) {
  document.getElementById("res-status").textContent = data.status || "Pending";
  document.getElementById("res-courier").textContent = data.courier || "Standard Courier";
  document.getElementById("res-tracking").textContent = data.tracking_id || "Awaiting Shipment";
  document.getElementById("res-est").textContent = data.estimated_delivery || "TBD";

  const steps = document.querySelectorAll(".track-step");
  steps.forEach(s => s.classList.remove("is-active", "is-complete"));

  const status = (data.status || "").toLowerCase();
  
  const mapping = {
    "placed": ["processing"],
    "confirmed": ["processing"],
    "processing": ["processing"],
    "packed": ["processing", "packed"],
    "shipped": ["processing", "packed", "shipped"],
    "in transit": ["processing", "packed", "shipped"],
    "out for delivery": ["processing", "packed", "shipped", "out"],
    "delivered": ["processing", "packed", "shipped", "out", "delivered"]
  };

  const activeSteps = mapping[status] || ["processing"];
  
  steps.forEach(step => {
    const slug = step.dataset.step;
    if (activeSteps.includes(slug)) {
      step.classList.add("is-complete");
      if (activeSteps[activeSteps.length - 1] === slug) {
        step.classList.add("is-active");
      }
    }
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  await initSite();
  trackOrder();
});
