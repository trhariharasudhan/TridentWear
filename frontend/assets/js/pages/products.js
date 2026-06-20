import { getWithFallback } from "../shared/api.js?v=20260430-v3";
import {
  bindProductCardActions,
  createEmptyMarkup,
  createSkeletonCards,
  initSite,
  productCardMarkup,
  startProgress,
  endProgress,
} from "../shared/site.js?v=20260430-v3";
import { normalizeProduct } from "../shared/catalog.js?v=20260430-v3";

/* ───────────────────────────────────────────
   STATE & CATEGORY MAP
─────────────────────────────────────────── */
let allProducts = [];
let activeCategory = "all";
let activeSearch = "";
let activeSort = "newest";
let activeFits = new Set();
let activeSizes = new Set();

const categoryLabels = {
  all:     "All Products",
  tshirt:  "T-Shirts",
};

/* ───────────────────────────────────────────
   READ ?cat= FROM URL
─────────────────────────────────────────── */
function hydrateFiltersFromURL() {
  const params = new URLSearchParams(window.location.search);
  activeCategory = categoryLabels[params.get("cat") || "all"] ? (params.get("cat") || "all") : "all";
  activeSearch = params.get("q") || "";
  activeSort = params.get("sort") || "newest";
  activeFits = new Set((params.get("fit") || "").split(",").filter(Boolean));
  activeSizes = new Set((params.get("size") || "").split(",").filter(Boolean));
}

function syncFilterInputs() {
  const search = document.querySelector("[data-shop-search]");
  const sort = document.querySelector("[data-shop-sort]");
  if (search) search.value = activeSearch;
  if (sort) sort.value = activeSort;
  document.querySelectorAll("[data-filter-fit]").forEach((input) => { input.checked = activeFits.has(input.value); });
  document.querySelectorAll("[data-filter-size]").forEach((input) => { input.checked = activeSizes.has(input.value); });
}

function syncURL() {
  const url = new URL(window.location.href);
  activeCategory === "all" ? url.searchParams.delete("cat") : url.searchParams.set("cat", activeCategory);
  activeSearch ? url.searchParams.set("q", activeSearch) : url.searchParams.delete("q");
  activeSort !== "newest" ? url.searchParams.set("sort", activeSort) : url.searchParams.delete("sort");
  activeFits.size ? url.searchParams.set("fit", [...activeFits].join(",")) : url.searchParams.delete("fit");
  activeSizes.size ? url.searchParams.set("size", [...activeSizes].join(",")) : url.searchParams.delete("size");
  window.history.replaceState({}, "", url.toString());
}

/* ───────────────────────────────────────────
   FILTER PRODUCTS
─────────────────────────────────────────── */
function filterProducts(cat) {
  const query = activeSearch.trim().toLowerCase();
  return allProducts.map(normalizeProduct).filter((product) => {
    if (cat !== "all" && product.category !== cat) return false;
    if (query && !`${product.name} ${product.description} ${product.fit_type} ${product.material}`.toLowerCase().includes(query)) return false;
    if (activeFits.size && ![...activeFits].some((fit) => product.categories.includes(fit))) return false;
    if (activeSizes.size && ![...activeSizes].some((size) => product.sizes.includes(size))) return false;
    return true;
  }).sort((a, b) => {
    if (activeSort === "price-asc") return a.price - b.price;
    if (activeSort === "price-desc") return b.price - a.price;
    if (activeSort === "popular") return Number(b.featured) - Number(a.featured) || b.stock - a.stock;
    return Number(b.id) - Number(a.id);
  });
}

/* ───────────────────────────────────────────
   RENDER PRODUCTS
─────────────────────────────────────────── */
function renderProducts(animate = true) {
  const grid = document.querySelector("[data-products-grid]");
  if (!grid) return;

  const filtered = filterProducts(activeCategory);

  // Update count
  const countEl = document.querySelector("[data-product-count]");
  if (countEl) countEl.textContent = filtered.length;

  if (!filtered.length) {
    grid.innerHTML = createEmptyMarkup(
      "No products found",
      "Try a different search, fit, size, or category.",
      "/products",
      "View All"
    );
    return;
  }

  if (animate) {
    grid.classList.add("fade-out");
    setTimeout(() => {
      grid.innerHTML = filtered.map(productCardMarkup).join("");
      bindProductCardActions(grid, filtered);
      grid.classList.remove("fade-out");
    }, 150);
  } else {
    grid.innerHTML = filtered.map(productCardMarkup).join("");
    bindProductCardActions(grid, filtered);
  }
}

/* ───────────────────────────────────────────
   UPDATE PAGE TITLE & BREADCRUMB
─────────────────────────────────────────── */
function updateLabels() {
  const label = categoryLabels[activeCategory] || "All Products";
  document.querySelectorAll("[data-active-category-label]").forEach(el => el.textContent = label);
  document.querySelectorAll("[data-active-category-label-h1]").forEach(el => el.textContent = label);
  document.title = `${label} | TridentWear`;
}

/* ───────────────────────────────────────────
   SYNC ACTIVE TAB
─────────────────────────────────────────── */
function syncTabs() {
  document.querySelectorAll("[data-main-category]").forEach(btn => {
    const isActive = btn.dataset.mainCategory === activeCategory;
    btn.classList.toggle("is-active", isActive);
  });

  // Scroll active tab into view
  const activeBtn = document.querySelector("[data-main-category].is-active");
  if (activeBtn) {
    activeBtn.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }
}

/* ───────────────────────────────────────────
   SWITCH CATEGORY
─────────────────────────────────────────── */
function switchCategory(cat) {
  if (cat === activeCategory) return;
  activeCategory = cat;

  syncURL();

  syncTabs();
  updateLabels();
  renderProducts(true);

  // Scroll to grid
  setTimeout(() => {
    document.querySelector("[data-products-grid]")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 100);
}

function initAdvancedFilters() {
  const search = document.querySelector("[data-shop-search]");
  const sort = document.querySelector("[data-shop-sort]");
  const drawer = document.querySelector("[data-filter-drawer]");
  let debounce = null;
  search?.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = window.setTimeout(() => {
      activeSearch = search.value;
      syncURL();
      renderProducts(true);
    }, 180);
  });
  sort?.addEventListener("change", () => {
    activeSort = sort.value;
    syncURL();
    renderProducts(true);
  });
  document.querySelectorAll("[data-filter-fit]").forEach((input) => {
    input.addEventListener("change", () => {
      input.checked ? activeFits.add(input.value) : activeFits.delete(input.value);
      syncURL();
      renderProducts(true);
    });
  });
  document.querySelectorAll("[data-filter-size]").forEach((input) => {
    input.addEventListener("change", () => {
      input.checked ? activeSizes.add(input.value) : activeSizes.delete(input.value);
      syncURL();
      renderProducts(true);
    });
  });
  document.querySelector("[data-filter-drawer-toggle]")?.addEventListener("click", () => drawer?.classList.add("is-open"));
  document.querySelectorAll("[data-filter-drawer-close]").forEach((button) => {
    button.addEventListener("click", () => drawer?.classList.remove("is-open"));
  });
  drawer?.addEventListener("click", (event) => {
    if (event.target === drawer) drawer.classList.remove("is-open");
  });
}

/* ───────────────────────────────────────────
   INIT TABS
─────────────────────────────────────────── */
function initTabs() {
  document.querySelectorAll("[data-main-category]").forEach(btn => {
    btn.addEventListener("click", () => switchCategory(btn.dataset.mainCategory));
  });
}

/* ───────────────────────────────────────────
   LOAD & INIT
─────────────────────────────────────────── */
async function loadAndRender() {
  try {
    startProgress();
    const grid = document.querySelector("[data-products-grid]");
    if (grid) grid.innerHTML = createSkeletonCards(8);
    allProducts = await getWithFallback(["/api/v1/products"]);
    if (!Array.isArray(allProducts)) allProducts = allProducts.products || [];

    hydrateFiltersFromURL();
    syncFilterInputs();
    syncTabs();
    updateLabels();
    renderProducts(false);
    initTabs();
    initAdvancedFilters();
  } catch (err) {
    console.error("Failed to load products:", err);
  } finally {
    endProgress();
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await initSite();
  await loadAndRender();
});
