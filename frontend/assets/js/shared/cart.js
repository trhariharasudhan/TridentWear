import { getAuthSession } from "./api.js";
import { DEFAULT_PRODUCTS } from "./mock-data.js";

const GUEST_KEY = "trident-cart-guest";

function getStorageKey() {
  const session = getAuthSession();
  if (session && session.user && session.user.id) {
    return `trident-cart-${session.user.id}`;
  }
  return GUEST_KEY;
}

export function resolveAvailableStock(product) {
  const pid = product?.id ? Number(product.id) : null;

  // 1. Authoritative dynamic catalogue in localStorage (if populated)
  if (pid) {
    try {
      const rawDb = localStorage.getItem("tridentwear-products-db");
      if (rawDb) {
        const list = JSON.parse(rawDb);
        const match = Array.isArray(list) ? list.find((p) => Number(p.id) === pid) : null;
        if (match && match.stock !== undefined && match.stock !== null) {
          const s = Number(match.stock);
          if (Number.isFinite(s) && !isNaN(s)) {
            return Math.max(0, Math.floor(s));
          }
        }
      }
    } catch (_) {}
  }

  // 2. Direct stock passed by caller / product data
  if (product && product.stock !== undefined && product.stock !== null) {
    const s = typeof product.stock === "number" ? product.stock : Number(product.stock);
    if (Number.isFinite(s) && !isNaN(s)) {
      return Math.max(0, Math.floor(s));
    }
  }

  // 3. Authoritative default catalogue fallback from mock-data
  if (pid) {
    try {
      const match = DEFAULT_PRODUCTS.find((p) => Number(p.id) === pid);
      if (match && match.stock !== undefined && match.stock !== null) {
        const s = Number(match.stock);
        if (Number.isFinite(s) && !isNaN(s)) {
          return Math.max(0, Math.floor(s));
        }
      }
    } catch (_) {}
  }

  // 4. Conservative fallback: never interpret missing stock as unlimited inventory.
  return 0;
}

function parseRequestedQuantity(options) {
  if (!options || typeof options !== "object" || !("qty" in options)) {
    // Default quantity when options.qty is not specified
    return { requestedQty: 1, isValid: true };
  }
  const raw = options.qty;
  if (
    raw === undefined ||
    raw === null ||
    raw === "" ||
    (typeof raw === "number" && !Number.isFinite(raw)) ||
    (typeof raw === "number" && !Number.isInteger(raw)) ||
    (typeof raw === "number" && raw <= 0) ||
    isNaN(Number(raw)) ||
    Number(raw) <= 0 ||
    !Number.isInteger(Number(raw))
  ) {
    return { requestedQty: 0, isValid: false };
  }
  return { requestedQty: Number(raw), isValid: true };
}

function emitChange(items) {
  window.dispatchEvent(
    new CustomEvent("trident:cart-change", {
      detail: {
        items,
        count: getCartCount(items),
        subtotal: getCartSubtotal(items),
        openDrawer: false,
      },
    }),
  );
}

export function loadCart() {
  try {
    const key = getStorageKey();
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveCart(items) {
  const key = getStorageKey();
  localStorage.setItem(key, JSON.stringify(items));
  emitChange(items);
  return items;
}

export function syncCart() {
  emitChange(loadCart());
}

export function getCartCount(items = loadCart()) {
  return items.reduce((total, item) => total + Number(item.qty || 0), 0);
}

export function getCartSubtotal(items = loadCart()) {
  return items.reduce((total, item) => total + Number(item.price || 0) * Number(item.qty || 0), 0);
}

export function addCartItem(product, options = {}) {
  const size = options?.size || product?.sizes?.[0] || "M";
  const { requestedQty, isValid } = parseRequestedQuantity(options);
  const availableStock = resolveAvailableStock(product);
  const items = loadCart();

  // Aggregate quantity for this product ID across all sizes
  const currentProductTotal = items
    .filter((item) => item.id === product?.id)
    .reduce((sum, item) => sum + Number(item.qty || 0), 0);

  let addedQty = 0;
  let status = "SUCCESS";

  if (!isValid) {
    status = "INVALID_QTY";
    addedQty = 0;
  } else if (availableStock <= 0) {
    status = "OUT_OF_STOCK";
    addedQty = 0;
  } else if (currentProductTotal >= availableStock) {
    status = "EXCEEDED";
    addedQty = 0;
  } else {
    const remainingStock = Math.max(0, availableStock - currentProductTotal);
    addedQty = Math.min(requestedQty, remainingStock);

    if (addedQty <= 0) {
      status = "EXCEEDED";
      addedQty = 0;
    } else if (addedQty < requestedQty) {
      status = "PARTIAL";
    } else {
      status = "SUCCESS";
    }
  }

  if (addedQty > 0) {
    const existing = items.find((item) => item.id === product.id && item.size === size);
    if (existing) {
      existing.qty += addedQty;
      if (availableStock > 0) existing.stock = availableStock;
    } else {
      items.push({
        id: product.id,
        name: product.name,
        price: product.price,
        image: product.image,
        size,
        qty: addedQty,
        stock: availableStock,
      });
    }
  }

  const saved = addedQty > 0 ? saveCart(items) : items;
  if (options?.openDrawer && addedQty > 0) {
    window.dispatchEvent(
      new CustomEvent("trident:cart-open-drawer", {
        detail: { items: saved },
      }),
    );
  }

  // Attach metadata to return array
  saved.success = addedQty > 0;
  saved.addedQty = addedQty;
  saved.requestedQty = requestedQty;
  saved.availableStock = availableStock;
  saved.remainingStock = Math.max(0, availableStock - (currentProductTotal + addedQty));
  saved.status = status;

  return saved;
}

/**
 * Merge guest cart into user cart after login.
 * Call this right after a successful auth session is saved.
 */
export function mergeGuestCartOnLogin() {
  try {
    const session = getAuthSession();
    if (!session || !session.user || !session.user.id) {
      return { success: false, reason: "NO_SESSION", mergedCount: 0, unmergedCount: 0 };
    }

    const guestRaw = localStorage.getItem(GUEST_KEY);
    if (!guestRaw) {
      return { success: true, mergedCount: 0, unmergedCount: 0, unmergedItems: [] };
    }

    const guestItems = JSON.parse(guestRaw);
    if (!Array.isArray(guestItems) || !guestItems.length) {
      localStorage.removeItem(GUEST_KEY);
      return { success: true, mergedCount: 0, unmergedCount: 0, unmergedItems: [] };
    }

    const userKey = `trident-cart-${session.user.id}`;
    const existingRaw = localStorage.getItem(userKey);
    const userItems = existingRaw ? JSON.parse(existingRaw) : [];

    let mergedCount = 0;
    let unmergedCount = 0;
    const remainingGuestItems = [];

    // Merge: add guest quantities into user cart respecting stock ceiling
    for (const gItem of guestItems) {
      const gQty = Math.max(0, Math.floor(Number(gItem.qty || 0)));
      if (gQty <= 0) continue;

      const stock = resolveAvailableStock({ id: gItem.id, stock: gItem.stock });

      const currentTotal = userItems
        .filter((i) => Number(i.id) === Number(gItem.id))
        .reduce((sum, i) => sum + Number(i.qty || 0), 0);

      const remaining = Math.max(0, stock - currentTotal);
      const qtyToAdd = Math.min(gQty, remaining);
      const unmergedRemainder = gQty - qtyToAdd;

      if (qtyToAdd > 0) {
        const match = userItems.find((i) => Number(i.id) === Number(gItem.id) && i.size === gItem.size);
        if (match) {
          match.qty += qtyToAdd;
          if (stock > 0) match.stock = stock;
        } else {
          userItems.push({ ...gItem, qty: qtyToAdd, stock });
        }
        mergedCount += qtyToAdd;
      }

      if (unmergedRemainder > 0) {
        remainingGuestItems.push({ ...gItem, qty: unmergedRemainder, stock });
        unmergedCount += unmergedRemainder;
      }
    }

    localStorage.setItem(userKey, JSON.stringify(userItems));

    // Preserve unmerged items in guest cart; only delete if all were merged
    if (remainingGuestItems.length > 0) {
      localStorage.setItem(GUEST_KEY, JSON.stringify(remainingGuestItems));
    } else {
      localStorage.removeItem(GUEST_KEY);
    }

    emitChange(userItems);

    const mergeResult = {
      success: true,
      mergedCount,
      unmergedCount,
      unmergedItems: remainingGuestItems,
      totalUserItems: getCartCount(userItems),
    };

    window.dispatchEvent(
      new CustomEvent("trident:cart-merged", {
        detail: mergeResult,
      }),
    );

    return mergeResult;
  } catch (err) {
    return { success: false, error: err?.message || String(err), mergedCount: 0, unmergedCount: 0 };
  }
}

export function updateCartItemQuantity(id, size, nextQty) {
  const cleanQty = Math.max(0, Math.floor(Number(nextQty) || 0));
  if (cleanQty <= 0) {
    return removeCartItem(id, size);
  }

  const items = loadCart();
  const existing = items.find((item) => Number(item.id) === Number(id) && item.size === size);
  if (!existing) return items;

  // Prefer authoritative current catalogue stock, falling back to cached stock
  const stock = resolveAvailableStock({ id, stock: existing.stock });

  // Other items of same product in cart across other sizes
  const otherQty = items
    .filter((item) => Number(item.id) === Number(id) && item.size !== size)
    .reduce((sum, item) => sum + Number(item.qty || 0), 0);

  const currentSizeQty = Number(existing.qty || 0);

  // If item is already overstocked (currentSizeQty + otherQty > stock)
  if (currentSizeQty + otherQty > stock) {
    if (cleanQty > currentSizeQty) {
      // Reject attempt to increase beyond existing overstocked level
      return items;
    }
    // Allow decreasing quantity safely
    existing.qty = cleanQty;
    existing.stock = stock;
    return saveCart(items);
  }

  // Normal stock ceiling enforcement
  const maxAllowedForThisSize = Math.max(0, stock - otherQty);
  if (cleanQty > maxAllowedForThisSize) {
    // Clamp to maximum allowed without exceeding stock
    existing.qty = maxAllowedForThisSize;
  } else {
    existing.qty = cleanQty;
  }

  existing.stock = stock;
  return saveCart(items);
}

export function removeCartItem(id, size) {
  return saveCart(loadCart().filter((item) => !(item.id === id && item.size === size)));
}

export function getFbtToken() {
  try {
    return localStorage.getItem("tridentwear-fbt-token") || null;
  } catch (_) {
    return null;
  }
}

export function setFbtToken(token) {
  try {
    if (token) {
      localStorage.setItem("tridentwear-fbt-token", String(token));
    } else {
      localStorage.removeItem("tridentwear-fbt-token");
    }
  } catch (_) {}
}

export function clearFbtToken() {
  try {
    localStorage.removeItem("tridentwear-fbt-token");
  } catch (_) {}
}

export function clearCart() {
  clearFbtToken();
  try {
    localStorage.removeItem("tridentwear-applied-coupon");
  } catch (_) {}
  return saveCart([]);
}
