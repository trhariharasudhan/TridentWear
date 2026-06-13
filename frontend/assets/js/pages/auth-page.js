import { post, saveAuthSession } from "../shared/api.js?v=20260430-v3";
import { mergeGuestCartOnLogin } from "../shared/cart.js?v=20260430-v3";
import { escapeHtml, getCurrentUser, initSite, pageUrl, refreshAuthState, showToast } from "../shared/site.js?v=20260430-v3";

function nextPath() {
  const params = new URLSearchParams(window.location.search);
  return normalizeNextPath(params.get("next") || "");
}

function normalizeNextPath(path) {
  const raw = String(path || "").trim();
  if (!raw) {
    return "";
  }

  const normalized = raw.startsWith("/") ? raw.slice(1) : raw;
  const routeMap = {
    "": pageUrl("/"),
    admin: pageUrl("/admin"),
    wishlist: pageUrl("/wishlist"),
    login: pageUrl("/login"),
    register: pageUrl("/register"),
    products: pageUrl("/products"),
    product: pageUrl("/product"),
    cart: pageUrl("/cart"),
    checkout: pageUrl("/checkout"),
    about: pageUrl("/about"),
    contact: pageUrl("/contact"),
    privacy: pageUrl("/privacy"),
    terms: pageUrl("/terms"),
    returns: pageUrl("/returns"),
    shipping: pageUrl("/shipping"),
    track: pageUrl("/track"),
  };

  return routeMap[normalized] || normalized;
}

function buildPath(path) {
  const next = nextPath();
  return next ? `${path}?next=${encodeURIComponent(next)}` : path;
}

function redirectAfterAuth(user) {
  if (user && user.profile_completed_status === false) {
    window.location.href = pageUrl("/profile-setup");
    return;
  }
  
  const next = nextPath();
  if (next) {
    window.location.href = next;
    return;
  }

  window.location.href = pageUrl(user.role === "admin" ? "/admin" : "/profile");
}

function renderAuthStatus() {
  const user = getCurrentUser();
  const status = document.querySelector("[data-auth-status]");
  if (!status) {
    return;
  }

  if (!user) {
    status.hidden = true;
    status.innerHTML = "";
    return;
  }

  status.hidden = false;
  status.innerHTML = `
    <div class="auth-status-card">
      <strong>Hello, ${escapeHtml(user.name.split(" ")[0] || user.name)}</strong>
      <span>Signed in as ${escapeHtml(user.email || user.phone)}</span>
    </div>
  `;
}

function wireSwitchLinks(mode) {
  const alternatePath = mode === "login" ? pageUrl("/register") : pageUrl("/login");
  document.querySelectorAll("[data-auth-switch]").forEach((link) => {
    link.setAttribute("href", buildPath(alternatePath));
  });
}

function setSubmitting(form, isSubmitting, idleLabel, pendingLabel) {
  const button = form.querySelector("button[type='submit']");
  if (!button) {
    return;
  }

  button.disabled = isSubmitting;
  button.textContent = isSubmitting ? pendingLabel : idleLabel;
}

function setButtonLoading(button, isLoading, idleLabel, loadingLabel) {
  if (!button) return;
  button.disabled = isLoading;
  button.textContent = isLoading ? loadingLabel : idleLabel;
}

function bindRegisterForm() {
  const form = document.querySelector("[data-register-form]");
  if (!form) {
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const name = form.querySelector("#register-name")?.value.trim() || "";
    const email = form.querySelector("#register-email")?.value.trim() || "";
    const password = form.querySelector("#register-password")?.value.trim() || "";
    const confirmPassword = form.querySelector("#register-confirm-password")?.value.trim() || "";

    if (!name || !email || !password || !confirmPassword) {
      showToast("Please complete every registration field.", "error");
      return;
    }

    if (password !== confirmPassword) {
      showToast("Passwords do not match.", "error");
      return;
    }

    setSubmitting(form, true, "Create Account", "Creating Account...");
    try {
      const data = await post("/api/v1/auth/register", {
        name,
        email,
        password,
        confirm_password: confirmPassword,
      });

      // Show dev OTP if present
      if (data.dev_otp) {
        showToast(data.message.replace(data.dev_otp, '***') + "\nDev OTP: " + data.dev_otp, "success");
      } else {
        showToast(data.message || "Please check your email for OTP.", "success");
      }
      setTimeout(() => {
        window.location.href = pageUrl(`/verify?email=${encodeURIComponent(email)}`);
      }, 3000); // give them time to read the OTP
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setSubmitting(form, false, "Create Account", "Creating Account...");
    }
  });
}

function bindOtpLogin() {
  const sendOtpBtn = document.getElementById("send-otp-btn");
  const resendOtpBtn = document.getElementById("resend-otp-btn");
  const mobileInput = document.getElementById("login-mobile");
  const countryInput = document.getElementById("login-country-code");
  const otpContainer = document.getElementById("otp-field-container");
  const otpInput = document.getElementById("login-otp");
  const otpStatus = document.querySelector("[data-otp-status]");
  const otpHelper = document.querySelector("[data-otp-helper]");

  if (!sendOtpBtn) return;

  let otpSent = false;
  let resendTimer = null;

  const resetOtpBoxes = () => {
    document.querySelectorAll(".otp-box").forEach((box) => { box.value = ""; });
    if (otpInput) otpInput.value = "";
  };

  const currentPayload = () => ({
    phone: mobileInput.value.replace(/\D/g, ""),
    country_code: countryInput?.value || "+91",
  });

  const startResendTimer = (seconds = 45) => {
    if (!resendOtpBtn) return;
    window.clearInterval(resendTimer);
    let remaining = Number(seconds || 45);
    resendOtpBtn.hidden = false;
    resendOtpBtn.disabled = true;
    resendOtpBtn.textContent = `Resend OTP in ${remaining}s`;
    resendTimer = window.setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        window.clearInterval(resendTimer);
        resendOtpBtn.disabled = false;
        resendOtpBtn.textContent = "Resend OTP";
        return;
      }
      resendOtpBtn.textContent = `Resend OTP in ${remaining}s`;
    }, 1000);
  };

  const sendOtp = async ({ isResend = false } = {}) => {
    const payload = currentPayload();
    if (!payload.phone || !/^[0-9]{10}$/.test(payload.phone)) {
      showToast("Please enter a valid 10-digit mobile number.", "error");
      return;
    }

    setButtonLoading(isResend ? resendOtpBtn : sendOtpBtn, true, isResend ? "Resend OTP" : "Send OTP", "Sending...");
    try {
      const data = await post("/api/v1/auth/send-otp", payload);
      otpSent = true;
      resetOtpBoxes();
      otpContainer.style.display = "block";
      sendOtpBtn.innerHTML = '<i class="fa-solid fa-shield-halved"></i> Verify & Login';
      if (otpHelper) otpHelper.textContent = `OTP sent to ${data.phone_masked || "your mobile number"}.`;
      if (otpStatus) {
        otpStatus.textContent = data.dev_otp
          ? `Development OTP: ${data.dev_otp}`
          : "Enter the 6-digit OTP before it expires.";
      }
      startResendTimer(data.resend_after || 45);
      document.querySelector(".otp-box")?.focus();
      showToast(data.dev_otp ? `OTP sent. Dev OTP: ${data.dev_otp}` : "OTP sent to your mobile.", "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      if (!isResend) {
        setButtonLoading(sendOtpBtn, false, "Send OTP", "Sending...");
      }
      if (otpSent) {
        sendOtpBtn.innerHTML = '<i class="fa-solid fa-shield-halved"></i> Verify & Login';
      }
    }
  };

  const verifyOtp = async () => {
    const payload = { ...currentPayload(), otp: otpInput.value.trim() };
    if (!payload.otp || payload.otp.length < 6) {
      showToast("Please enter the 6-digit OTP.", "error");
      return;
    }

    setButtonLoading(sendOtpBtn, true, "Verify & Login", "Verifying...");
    try {
      const data = await post("/api/v1/auth/verify-otp", payload);
      showToast("Mobile verified. Welcome to TridentWear.", "success");
      saveAuthSession({ token: data.token, user: data.user });
      await refreshAuthState();
      redirectAfterAuth(data.user);
    } catch (err) {
      showToast(err.message, "error");
      sendOtpBtn.innerHTML = '<i class="fa-solid fa-shield-halved"></i> Verify & Login';
    } finally {
      sendOtpBtn.disabled = false;
    }
  };

  mobileInput?.addEventListener("input", () => {
    mobileInput.value = mobileInput.value.replace(/\D/g, "").slice(0, 10);
    otpSent = false;
    otpContainer.style.display = "none";
    sendOtpBtn.innerHTML = '<i class="fa-solid fa-mobile-screen-button"></i> Send OTP';
    if (resendOtpBtn) resendOtpBtn.hidden = true;
  });

  countryInput?.addEventListener("change", () => {
    otpSent = false;
    otpContainer.style.display = "none";
    sendOtpBtn.innerHTML = '<i class="fa-solid fa-mobile-screen-button"></i> Send OTP';
    if (resendOtpBtn) resendOtpBtn.hidden = true;
  });

  sendOtpBtn.addEventListener("click", async () => {
    if (!otpSent) await sendOtp();
    else await verifyOtp();
  });

  resendOtpBtn?.addEventListener("click", () => {
    sendOtp({ isResend: true });
  });
}

function bindLoginTabs() {
  const emailBlock = document.getElementById("email-login-block");
  const otpBlock = document.getElementById("otp-login-block");
  const emailTab = document.getElementById("btn-tab-email");
  const otpTab = document.getElementById("btn-tab-otp");
  if (!emailBlock || !otpBlock || !emailTab || !otpTab) return;

  const switchTab = (tab) => {
    const emailActive = tab === "email";
    emailBlock.style.display = emailActive ? "block" : "none";
    otpBlock.style.display = emailActive ? "none" : "block";
    emailTab.classList.toggle("is-active", emailActive);
    otpTab.classList.toggle("is-active", !emailActive);
  };

  document.querySelectorAll("[data-login-tab]").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.loginTab));
  });
}

function bindPasswordToggles() {
  document.querySelectorAll("[data-toggle-password]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.togglePassword);
      const icon = button.querySelector("i");
      if (!input || !icon) return;
      input.type = input.type === "password" ? "text" : "password";
      icon.className = input.type === "password" ? "fa-regular fa-eye" : "fa-regular fa-eye-slash";
    });
  });
}

function bindOtpBoxes() {
  const boxes = Array.from(document.querySelectorAll(".otp-box"));
  const target = document.getElementById("login-otp");
  if (!boxes.length || !target) return;
  boxes.forEach((box, index) => {
    box.addEventListener("input", () => {
      box.value = box.value.replace(/\D/g, "").slice(0, 1);
      if (box.value && index < boxes.length - 1) boxes[index + 1].focus();
      target.value = boxes.map((entry) => entry.value).join("");
    });
    box.addEventListener("paste", (event) => {
      event.preventDefault();
      const pasted = event.clipboardData.getData("text").replace(/\D/g, "").slice(0, boxes.length);
      pasted.split("").forEach((digit, digitIndex) => {
        if (boxes[digitIndex]) boxes[digitIndex].value = digit;
      });
      target.value = boxes.map((entry) => entry.value).join("");
      boxes[Math.min(pasted.length, boxes.length) - 1]?.focus();
    });
    box.addEventListener("keydown", (event) => {
      if (event.key === "Backspace" && !box.value && index > 0) boxes[index - 1].focus();
    });
  });
}

function bindPasswordStrength() {
  const password = document.getElementById("register-password");
  const wrap = document.getElementById("pw-strength-wrap");
  const fill = document.getElementById("pw-fill");
  const label = document.getElementById("pw-label");
  if (!password || !wrap || !fill || !label) return;

  password.addEventListener("input", () => {
    const val = password.value;
    if (!val) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    let score = 0;
    if (val.length >= 8) score++;
    if (/[A-Z]/.test(val)) score++;
    if (/[0-9]/.test(val)) score++;
    if (/[^A-Za-z0-9]/.test(val)) score++;
    const levels = [
      { w: "25%", c: "#dc3545", t: "Weak" },
      { w: "50%", c: "#fd7e14", t: "Fair" },
      { w: "75%", c: "#ffc107", t: "Good" },
      { w: "100%", c: "#198754", t: "Strong" },
    ];
    const level = levels[score - 1] || levels[0];
    fill.style.width = level.w;
    fill.style.background = level.c;
    label.textContent = level.t;
    label.style.color = level.c;
  });
}

window.handleGoogleCredentialResponse = async (response) => {
  if (!response || !response.credential) return;
  
  showToast("Verifying with Google...", "info");
  try {
    const data = await post("/api/v1/auth/google", { credential: response.credential });
    saveAuthSession({ token: data.token, user: data.user });
    await refreshAuthState();
    showToast("Signed in with Google!", "success");
    redirectAfterAuth(data.user);
  } catch (err) {
    showToast(err.message, "error");
  }
};

function bindGoogleLogin() {
  const btns = document.querySelectorAll("#google-login-btn, .btn-social");
  btns.forEach(btn => {
    if (!btn.textContent.toLowerCase().includes("google")) return;
    if (btn.dataset.boundGoogle) return;
    btn.dataset.boundGoogle = "true";

    btn.addEventListener("click", () => {
      // Google OAuth is handled by the GIS library on the login page via
      // handleGoogleCredentialResponse. On the register page, redirect to login.
      showToast("Please use the Google button on the login page for Google sign-in.", "info");
      setTimeout(() => { window.location.href = "/login"; }, 1200);
    });
  });
}

function bindForgotPassword() {
  const link = document.getElementById("forgot-password-link");
  if (!link) return;
  link.addEventListener("click", async (e) => {
    e.preventDefault();
    // Password reset via email/OTP is not yet available.
    // Show a helpful message directing the user to contact support.
    showToast("Password reset is not yet available. Please contact support via the chat or contact page.", "info");
  });
}

function bindLoginForm() {
  const form = document.querySelector("[data-login-form]");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    const emailBlock = document.getElementById("email-login-block");
    if (emailBlock && emailBlock.style.display === "none") {
      event.preventDefault();
      return;
    }

    event.preventDefault();

    const email = form.querySelector("#login-email")?.value.trim() || "";
    const password = form.querySelector("#login-password")?.value.trim() || "";

    if (!email || !password) {
      showToast("Enter your email and password.", "error");
      return;
    }

    setSubmitting(form, true, "Login", "Signing In...");
    try {
      const data = await post("/api/v1/auth/login", { email, password });
      saveAuthSession({ token: data.token, user: data.user });
      mergeGuestCartOnLogin();
      await refreshAuthState();
      renderAuthStatus();
      redirectAfterAuth(data.user);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setSubmitting(form, false, "Login", "Signing In...");
    }
  });
}

export async function initAuthPage(mode) {
  await initSite();
  wireSwitchLinks(mode);
  renderAuthStatus();
  bindRegisterForm();
  bindLoginForm();
  bindGoogleLogin();
  bindPasswordToggles();
  bindPasswordStrength();
  if (mode === "login") {
    bindLoginTabs();
    bindOtpBoxes();
    bindOtpLogin();
    bindForgotPassword();
  }
}
