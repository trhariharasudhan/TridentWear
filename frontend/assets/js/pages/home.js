import { get } from "../shared/api.js?v=20260430-v3";
import {
  bindProductCardActions,
  createSkeletonCards,
  formatCurrency,
  initSite,
  pageUrl,
  productCardMarkup,
  resolveAssetUrl,
  startProgress,
  endProgress,
  escapeHtml,
} from "../shared/site.js?v=20260430-v3";
import { createGlobalScrollManager } from "../utilities/scroll-throttle.js";

/* ─── Hero Slider ─── */
function initHeroSlider() {
  const slides = document.querySelectorAll(".hero-slide");
  const dots   = document.querySelectorAll(".hero-dot");
  const prev   = document.querySelector("[data-hero-prev]");
  const next   = document.querySelector("[data-hero-next]");
  if (!slides.length) return;

  let current  = 0;
  let timer    = null;

  function goTo(index) {
    slides[current].classList.remove("is-active");
    dots[current]?.classList.remove("is-active");
    current = (index + slides.length) % slides.length;
    slides[current].classList.add("is-active");
    dots[current]?.classList.add("is-active");
  }

  function autoplay() {
    clearInterval(timer);
    timer = setInterval(() => goTo(current + 1), 4500);
  }

  prev?.addEventListener("click", () => { goTo(current - 1); autoplay(); });
  next?.addEventListener("click", () => { goTo(current + 1); autoplay(); });
  dots.forEach((dot, i) => dot.addEventListener("click", () => { goTo(i); autoplay(); }));

  // Pause on hover
  document.querySelector(".hero-banner")?.addEventListener("mouseenter", () => clearInterval(timer));
  document.querySelector(".hero-banner")?.addEventListener("mouseleave", autoplay);

  autoplay();
}

/* ─── Featured Products (New Arrivals) ─── */
async function loadFeaturedProducts() {
  const grid = document.querySelector("[data-featured-grid]");
  const spotlight = document.querySelector("[data-featured-drop-product]");
  if (!grid && !spotlight) return;

  if (grid) grid.innerHTML = createSkeletonCards(4);
  startProgress();

  try {
    const data     = await get("/api/v1/products?featured=true");
    const products = (Array.isArray(data) ? data : data.products || []).slice(0, 4);
    if (!products.length) {
      if (grid) grid.innerHTML = "";
      if (spotlight) spotlight.closest("[data-featured-drop]")?.remove();
      return;
    }
    if (grid) {
      grid.innerHTML = products.map(productCardMarkup).join("");
      bindProductCardActions(grid, products);
    }
    if (spotlight) {
      const heroProduct = products[0];
      spotlight.innerHTML = productCardMarkup(heroProduct);
      bindProductCardActions(spotlight, [heroProduct]);
    }
  } catch {
    if (grid) grid.innerHTML = "";
    if (spotlight) spotlight.closest("[data-featured-drop]")?.remove();
  } finally {
    endProgress();
  }
}

/* ─── Trending Products (horizontal scroll) ─── */
async function loadTrendingProducts() {
  const wrap = document.querySelector("[data-trending-grid]");
  if (!wrap) return;

  wrap.innerHTML = createSkeletonCards(6);

  try {
    const data     = await get("/api/v1/products");
    const products = (Array.isArray(data) ? data : data.products || []).slice(0, 8);
    if (!products.length) { wrap.closest(".trending-section")?.remove(); return; }
    wrap.innerHTML = products.map(productCardMarkup).join("");
    bindProductCardActions(wrap, products);
  } catch {
    wrap.closest(".trending-section")?.remove();
  }
}

/* ─── Customer Count Ticker ─── */
async function loadStats() {
  const statNumbers = document.querySelectorAll("[data-count], [data-rating]");
  if (!statNumbers.length) return;

  // Get stats from API or use defaults
  let statsData = {
    customers: 15000,
    orders: 25000,
    rating: 4.8
  };

  try {
    const data = await get("/api/v1/orders/stats");
    if (data?.customers) statsData.customers = data.customers;
    if (data?.orders) statsData.orders = data.orders;
    if (data?.rating) statsData.rating = data.rating;
  } catch { /* use defaults */ }

  const animateNumber = (element, target, duration = 1800) => {
    const isRating = element.hasAttribute("data-rating");
    if (isRating) {
      // For rating, just set it directly since it's typically 4-5
      element.textContent = target;
      return;
    }

    const start = performance.now();
    const startVal = 0;

    const animate = (now) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      
      // Ease-out cubic for smooth deceleration
      const easeProgress = 1 - Math.pow(1 - progress, 3);
      const currentVal = Math.floor(easeProgress * target);
      
      element.textContent = currentVal;
      
      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        element.textContent = target;
      }
    };

    requestAnimationFrame(animate);
  };

  // Animate each stat
  statNumbers.forEach((el) => {
    if (el.hasAttribute("data-count")) {
      const target = parseInt(el.getAttribute("data-count"));
      animateNumber(el, target);
    } else if (el.hasAttribute("data-rating")) {
      animateNumber(el, parseFloat(el.getAttribute("data-rating")));
    }
  });
}

/* ─── Newsletter ─── */
function initNewsletter() {
  const form = document.querySelector("[data-newsletter-form]");
  if (!form) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = form.querySelector("input[type=email]");
    const btn   = form.querySelector("button[type=submit]");
    const prev  = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-check"></i> Subscribed!';
    btn.disabled  = true;
    input.value   = "";
    setTimeout(() => { btn.innerHTML = prev; btn.disabled = false; }, 3000);
  });
}

/* ─── Scroll Reveal ─── */
function initScrollReveal() {
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
    // Already in viewport? Reveal immediately with stagger
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight) {
      const delay = parseInt(el.dataset.delay || 0);
      setTimeout(() => el.classList.add("is-visible"), delay);
    } else {
      observer.observe(el);
    }
  });
}

/* ─── Hero Parallax ─── */
function initHeroParallax() {
  const bg = document.querySelector(".hero-bg-gradient");
  if (!bg || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const scrollManager = createGlobalScrollManager();
  scrollManager.onScroll((scrollY) => {
    const offset = scrollY * 0.3;
    bg.style.transform = `translateY(${offset}px) scale(1.1)`;
  });
}

/* ─── Recently Viewed ─── */
function loadRecentlyViewed() {
  const section = document.getElementById("recently-viewed-section");
  const grid = document.getElementById("recently-viewed-grid");
  const clearBtn = document.getElementById("clear-recently-viewed");
  if (!section || !grid) return;

  const RV_KEY = "trident_recently_viewed";
  const items = JSON.parse(localStorage.getItem(RV_KEY) || "[]");
  if (!items.length) return;

  // Only show up to 4 cards
  const toShow = items.slice(0, 4);
  grid.innerHTML = toShow.map(p => {
    const productUrl = pageUrl(`/product?id=${p.id}`);
    const img = resolveAssetUrl(p.image || "assets/images/Logo.png");
    return `
      <article class="product-card reveal" style="cursor:pointer;" data-recent-product-link="${escapeHtml(productUrl)}">
        <div class="product-media" style="position:relative; overflow:hidden;">
          <img src="${escapeHtml(img)}" alt="${escapeHtml(p.name)}" loading="lazy" class="product-image">
        </div>
        <div class="product-body">
          <span class="product-type">${escapeHtml(p.category || "T-Shirt")}</span>
          <h3 class="product-name">${escapeHtml(p.name)}</h3>
          <div class="product-footer">
            <strong class="product-price">${formatCurrency(p.price)}</strong>
          </div>
          <a href="${productUrl}" class="btn btn-outline" style="width:100%;text-align:center;display:block;margin-top:0.75rem;padding:0.5rem;font-size:0.85rem;">View Again</a>
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

/* ─── Sticky mobile CTA — show after hero ─── */
function initStickyCTA() {
  const cta = document.getElementById("sticky-mob-cta");
  if (!cta) return;
  const hero = document.querySelector(".hero-premium");
  const threshold = hero ? hero.offsetHeight * 0.8 : 400;
  window.addEventListener("scroll", () => {
    cta.style.transform = window.scrollY > threshold ? "translateY(0)" : "translateY(100%)";
  }, { passive: true });
  cta.style.transform = "translateY(100%)";
  cta.style.transition = "transform 0.35s ease";
}

/* ─── Boot ─── */
window.addEventListener("DOMContentLoaded", async () => {
  document.body.classList.add("js-loaded");
  await initSite();
  // initHeroSlider(); // Disabled: No slider element exists on active homepage
  initNewsletter();
  initScrollReveal();
  initStickyCTA();
  initHeroParallax();
  loadRecentlyViewed();
  loadStats();
  loadFeaturedProducts();
  loadTrendingProducts();
});
