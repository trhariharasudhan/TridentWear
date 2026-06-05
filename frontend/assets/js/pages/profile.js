import { escapeHtml, getCurrentUser, initSite, pageUrl, showToast } from "../shared/site.js?v=20260430-v3";
import { get, request } from "../shared/api.js?v=20260430-v3";

async function loadProfile() {
  await initSite();
  const user = getCurrentUser();

  if (!user) {
    window.location.href = pageUrl("/login");
    return;
  }

  let accountProfile = { addresses: [], settings: {} };
  try {
    accountProfile = await get("/api/v1/account/profile");
  } catch (_) {
    accountProfile = JSON.parse(localStorage.getItem(`trident-profile-${user.id}`) || "{\"addresses\":[],\"settings\":{}}");
  }

  // Split name for firstname and lastname
  const names = (user.name || "").split(" ");
  const firstName = names[0] || "N/A";
  const lastName = names.length > 1 ? names.slice(1).join(" ") : "";

  const welcomeText = document.getElementById("welcome-message-text");
  if (welcomeText) {
    const fullName = user.name || firstName;
    if (user.gender === "Mr") {
      welcomeText.textContent = `👉 Mr. ${fullName}, welcome to your Trident Wear account`;
    } else if (user.gender === "Miss") {
      welcomeText.textContent = `👉 Miss ${fullName}, welcome to your Trident Wear account`;
    } else {
      welcomeText.textContent = `👉 Welcome ${fullName}, to your Trident Wear account`;
    }
  }

  // Sidebar Updates
  const sidebarName = document.getElementById("sidebar-name");
  const sidebarEmail = document.getElementById("sidebar-email");
  const sidebarRole = document.getElementById("sidebar-role");

  // Show Mr./Miss. prefix in yellow banner based on gender set during profile setup
  if (sidebarName) {
    const fullName = user.name || "N/A";
    if (user.gender === "Mr") {
      sidebarName.textContent = `Mr. ${fullName}`;
    } else if (user.gender === "Miss") {
      sidebarName.textContent = `Miss ${fullName}`;
    } else {
      sidebarName.textContent = fullName;
    }
  }
  if (sidebarEmail) sidebarEmail.textContent = user.email || "N/A";
  if (sidebarRole) sidebarRole.textContent = user.role === "admin" ? "(Admin)" : "(Member)";

  const year = new Date().getFullYear().toString().slice(-2);
  const paddedId = String(user.id).padStart(3, '0');
  // Format: TW26003 (no dashes)
  const generatedId = `TW${year}${paddedId}`;

  const customerIdSpan = document.getElementById("sidebar-customer-id");
  const referralIdSpan = document.getElementById("sidebar-referral-id");
  if(customerIdSpan) {
     customerIdSpan.textContent = generatedId;
  }
  if(referralIdSpan) {
     // Referral code same format as customer ID
     referralIdSpan.textContent = generatedId;
  }

  // Content Updates
  const emailInput = document.getElementById("profile-email-input");
  const firstNameInput = document.getElementById("profile-firstname");
  const lastNameInput = document.getElementById("profile-lastname");

  if (emailInput) emailInput.value = user.email || "N/A";
  if (firstNameInput) firstNameInput.value = firstName !== "N/A" ? firstName : "";
  if (lastNameInput) lastNameInput.value = lastName;
  const mobileInput = document.getElementById("profile-mobile");
  if (mobileInput) mobileInput.value = user.phone || "";

  // Setup tabs
  const tabLinks = document.querySelectorAll("[data-tab]");
  const sections = document.querySelectorAll(".profile-section-tab");

  tabLinks.forEach(link => {
    link.addEventListener("click", e => {
      e.preventDefault();
      
      const targetId = "section-" + link.getAttribute("data-tab");
      sections.forEach(sec => sec.style.display = "none");

      const targetPanel = document.getElementById(targetId);
      if (targetPanel) {
        targetPanel.style.display = "block";
      }

      tabLinks.forEach(l => {
        l.style.color = "#555";
        l.style.fontWeight = "normal";
      });
      link.style.color = "#117864";
      link.style.fontWeight = "600";
    });
  });

  // Fetch Orders
  const ordersContainer = document.getElementById("orders-container");
  if (ordersContainer) {
    try {
      const data = await get("/api/v1/orders");
      if (data && data.orders && data.orders.length > 0) {
        let html = '<div style="text-align: left;">';
        data.orders.forEach(o => {
          html += `
            <div style="border: 1px solid #ddd; padding: 1rem; margin-bottom: 1rem; border-radius: 4px;">
              <div style="display: flex; justify-content: space-between; margin-bottom: 1rem;">
                <strong>Order ID: ${escapeHtml(o.order_id)}</strong>
                <span style="color:var(--primary); font-weight: bold;">${escapeHtml(String(o.status || "confirmed").toUpperCase())}</span>
              </div>
              <p style="margin-bottom: 0.5rem; color: #555;">Date: ${new Date(o.created_at).toLocaleDateString()}</p>
              <p style="margin-bottom: 0.5rem; color: #555;">Total: ₹${o.subtotal}</p>
              <a href="${pageUrl(`/track?id=${o.order_id}`)}" class="btn btn-outline" style="padding: 0.25rem 1rem; font-size: 0.85rem;">Track</a>
            </div>
          `;
        });
        html += '</div>';
        ordersContainer.innerHTML = html;
      } else {
        ordersContainer.innerHTML = '<p style="font-size: 1.15rem; color: #555;">You have no recent orders.</p>';
      }
    } catch (err) {
      ordersContainer.innerHTML = '<p style="font-size: 1.15rem; color: #555;">Error loading orders.</p>';
    }
  }

  // Address Edit Modal Logic (structured fields)
  const addressDisplay = document.getElementById("address-display");
  const addressModal = document.getElementById("address-modal");
  const btnSaveAddress = document.getElementById("btn-save-address");
  const btnCancelAddress = document.getElementById("btn-cancel-address");
  const btnEditAddress = document.getElementById("btn-edit-address");

  // Store address object
  let savedAddress = accountProfile.addresses?.find((address) => String(address.id) === String(accountProfile.default_address_id)) || accountProfile.addresses?.[0] || {};
  if (addressDisplay && savedAddress.street) {
    addressDisplay.textContent = formatAddressDisplay(savedAddress);
    addressDisplay.style.color = "#333";
  }

  function openAddressModal() {
    if (document.getElementById("addr-street")) document.getElementById("addr-street").value = savedAddress.street || "";
    if (document.getElementById("addr-area")) document.getElementById("addr-area").value = savedAddress.area || "";
    if (document.getElementById("addr-city")) document.getElementById("addr-city").value = savedAddress.city || "";
    if (document.getElementById("addr-state")) document.getElementById("addr-state").value = savedAddress.state || "";
    if (document.getElementById("addr-pin")) document.getElementById("addr-pin").value = savedAddress.pin || "";
    if (addressModal) addressModal.style.display = "flex";
    setTimeout(() => { document.getElementById("addr-street")?.focus(); }, 100);
  }

  function formatAddressDisplay(addr) {
    const parts = [addr.street, addr.area, addr.city, addr.state, addr.pin].filter(Boolean);
    return parts.join(", ");
  }

  if (addressDisplay) addressDisplay.addEventListener("click", openAddressModal);
  if (btnEditAddress) btnEditAddress.addEventListener("click", (e) => { e.preventDefault(); openAddressModal(); });
  if (btnCancelAddress) btnCancelAddress.addEventListener("click", () => { if (addressModal) addressModal.style.display = "none"; });

  if (btnSaveAddress) {
    btnSaveAddress.addEventListener("click", () => {
      const street = document.getElementById("addr-street")?.value.trim() || "";
      const area = document.getElementById("addr-area")?.value.trim() || "";
      const city = document.getElementById("addr-city")?.value.trim() || "";
      const state = document.getElementById("addr-state")?.value.trim() || "";
      const pin = document.getElementById("addr-pin")?.value.trim() || "";

      if (!street || !city || !state || !pin) {
        showToast("Please fill Street, City, State and PIN Code.", "error");
        return;
      }
      if (!/^\d{6}$/.test(pin)) {
        showToast("Enter a valid 6-digit PIN code.", "error");
        return;
      }

      savedAddress = { id: savedAddress.id || `addr_${Date.now()}`, label: "Default shipping", street, area, city, state, pin, country: "India" };
      const formatted = formatAddressDisplay(savedAddress);
      if (addressDisplay) {
        addressDisplay.textContent = formatted;
        addressDisplay.style.color = "#333";
      }
      if (addressModal) addressModal.style.display = "none";
      saveProfile({ addresses: [savedAddress], default_address_id: savedAddress.id });
    });
  }

  const profileForm = document.getElementById("profile-update-form");
  profileForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const fullName = [firstNameInput?.value.trim(), lastNameInput?.value.trim()].filter(Boolean).join(" ");
    const gender = document.querySelector("input[name='title']:checked")?.value || user.gender || "";
    saveProfile({ name: fullName || user.name, phone: mobileInput?.value.trim() || "", gender });
  });

  async function saveProfile(payload) {
    const nextProfile = {
      ...accountProfile,
      ...payload,
      addresses: payload.addresses || accountProfile.addresses || [],
    };
    try {
      const saved = await request("/api/v1/account/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      accountProfile = saved.profile || saved;
      showToast("Profile saved.", "success");
    } catch (error) {
      localStorage.setItem(`trident-profile-${user.id}`, JSON.stringify(nextProfile));
      showToast("Saved locally. It will sync when account APIs are available.", "success");
    }
  }

  // Password Modal Logic
  const btnChangePwd = document.getElementById("btn-change-password");
  const pwdModal = document.getElementById("password-modal");
  const btnClosePwd = document.getElementById("close-password-modal");
  const pwdForm = document.getElementById("password-form");

  if (btnChangePwd && pwdModal && btnClosePwd && pwdForm) {
    btnChangePwd.addEventListener("click", (e) => {
      e.preventDefault();
      pwdModal.style.display = "flex";
    });

    btnClosePwd.addEventListener("click", () => {
      pwdModal.style.display = "none";
      pwdForm.reset();
    });

    pwdForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const current = document.getElementById("current-password").value;
      const newPwd = document.getElementById("new-password").value;
      const confirm = document.getElementById("confirm-password").value;

      if (newPwd !== confirm) {
        showToast("New passwords do not match!", "error");
        return;
      }
      if (newPwd.length < 6) {
        showToast("Password must be at least 6 characters.", "warning");
        return;
      }

      // Call the password change API
      try {
        await request("/api/v1/account/password-change", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current_password: current, new_password: newPwd }),
        });
        showToast("Password successfully changed!", "success");
        pwdModal.style.display = "none";
        pwdForm.reset();
      } catch (err) {
        showToast(err.message || "Failed to change password. Check your current password.", "error");
      }
    });
  }
}

window.addEventListener("DOMContentLoaded", loadProfile);
