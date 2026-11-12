// TridentWear storefront configuration.
//
// apiBase — where the FastAPI backend lives.
//   ''  => same origin (backend serves this site: local dev, Docker, Render).
//   'https://your-api.onrender.com' => GitHub Pages frontend talking to a hosted API.
// If no backend answers, the site runs in DEMO mode (browser-only data, simulated payments).
export const CONFIG = {
  apiBase: (window.TW_API_BASE ?? '').replace(/\/$/, ''),
  forceDemo: false,
  healthTimeoutMs: 2500,

  // Business details — placeholders until launch (edit here, used across the site)
  brand: {
    name: 'TridentWear',
    email: 'hello@tridentwear.in',
    phone: '+91 90000 00000',
    whatsapp: '919000000000',
    address: 'TridentWear Studio, 2nd Floor, 100 Feet Road, BTM Layout, Bengaluru, Karnataka 560076',
    instagram: 'https://instagram.com/tridentwear',
    gstin: 'GSTIN to be added',
  },

  // The backend charges no shipping fee today; keep the UI honest and in sync.
  shippingFee: 0,
  returnDays: 7,
  demoAdmin: { email: 'admin@tridentwear.in', password: 'Admin@123' },
};
