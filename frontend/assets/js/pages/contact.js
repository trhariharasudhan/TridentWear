import { post } from "../shared/api.js?v=20260430-v3";
import { escapeHtml, initSite, showToast } from "../shared/site.js?v=20260430-v3";

window.addEventListener("DOMContentLoaded", async () => {
  await initSite();

  const form = document.querySelector("[data-contact-form]");
  const status = document.querySelector("[data-contact-status]");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      name: form.querySelector("#contact-name")?.value.trim() || "",
      email: form.querySelector("#contact-email")?.value.trim() || "",
      message: form.querySelector("#contact-message")?.value.trim() || "",
    };

    if (!payload.name || !payload.email || !payload.message) {
      showToast("Please fill in all fields.", "error");
      return;
    }

    const btn = form.querySelector("button[type='submit']");
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Sending…";

    try {
      await post("/api/v1/contact", payload);
      form.reset();
      if (status) {
        status.innerHTML = `<div class="helper-note success">
          <strong>Message sent!</strong> We'll reply from the Trident desk within 24 hours.
        </div>`;
      }
      showToast("Message sent successfully.");
    } catch (error) {
      if (status) {
        status.innerHTML = `<div class="helper-note danger">${escapeHtml(error.message || "Failed to send. Please email us directly.")}</div>`;
      }
      showToast(error.message || "Failed to send message.", "error");
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
});
