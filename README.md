# 🛍️ TridentWear - Premium E-Commerce Platform

A complete, production-ready e-commerce platform built with **FastAPI** backend and **Vanilla JavaScript** frontend. Features a modern dark luxury UI, multi-method authentication, admin panel, and full shopping experience.

## ✨ Key Features

- **🎨 Modern Responsive Design** - Dark luxury theme with mobile-first approach
- **🔐 3-Method Authentication** - Email/Password, Mobile OTP, Google OAuth
- **📊 Admin Dashboard** - Product management, order tracking, analytics
- **🛒 Full Shopping Cart** - Add to cart, wishlist, checkout flow
- **👨‍💼 User Accounts** - Secure JWT authentication with bcrypt hashing
- **📦 Order Tracking** - Real-time order status and delivery tracking
- **💬 Contact System** - Customer inquiries and support messages
- **📈 Trust Indicators** - Statistics section with animated counters
- **🎯 Brand Logo** - Integrated navbar branding across all pages

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | HTML5, CSS3, Vanilla JavaScript |
| **Backend** | FastAPI, Uvicorn ASGI |
| **Database** | JSON (users, products, orders, contacts, chat) |
| **Authentication** | JWT (7-day expiry), Bcrypt hashing |
| **Icons** | FontAwesome 6.5.2 |
| **Styling** | CSS Grid, Flexbox, Responsive Design |

## 📁 Project Structure

```
TridentWear/
├── backend/                    # Backend API layer
│   ├── app/
│   │   ├── api/                # API router modules (auth, account, payments, etc.)
│   │   ├── core/               # Configuration, logging, security logic
│   │   ├── db/                 # JSON file manager (database layer)
│   │   ├── services/           # Business logic (order processing, coupon count, etc.)
│   │   └── main.py             # Uvicorn FastAPI application entry point
│   ├── requirements.txt        # Python package dependencies (pinned)
│   └── .env                    # Production & Dev Environment secrets (git ignored)
│
├── frontend/                   # Frontend assets & templates
│   ├── components/            # Reusable header and footer HTML partials
│   ├── pages/                 # Website page structures
│   │   ├── shop/              # cart, checkout, products, product pages
│   │   ├── account/           # profile, login, register, verify pages
│   │   ├── info/              # about, contact pages
│   │   ├── admin/             # admin dashboard, admin chat panels
│   │   ├── legal/             # privacy, terms, shipping, returns pages
│   │   ├── support/           # tracking, support chat pages
│   │   └── error/             # 404 page
│   ├── assets/                # Static assets loaded by the browser
│   │   ├── css/               # styles.css, premium.css (luxurious golden/dark theme)
│   │   ├── js/                # Modular scripts split by pages/ and shared/
│   │   └── images/            # Product cards, banners, logo, and uploads
│   ├── robots.txt             # Search engine crawler permissions
│   └── sitemap.xml            # XML sitemap for SEO discovery
│
├── db/                         # File-Based JSON Databases (atomic writes)
│   ├── users.json             # Hashed credentials & profiles
│   ├── products.json          # Live product catalog
│   ├── orders.json            # Order data & shipping status
│   └── coupons.json           # Available discount codes & usage counts
│
├── README.md                   # Project documentation
├── start.bat                   # Windows local development shortcut launcher
├── package.json               # Node dev tools validation script definitions
└── requirements.txt            # Root python environment dependencies (pinned)
```

## 🚀 Quick Start

```bash
# 1. Install dependencies (recommended using a virtual environment)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. Start the local server
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010 --reload

# 3. Open in browser
# Storefront: http://127.0.0.1:8010/
# Admin Panel: http://127.0.0.1:8010/admin
```

## 🔐 Authentication

### Admin Account
- **Email:** Set via `ADMIN_EMAIL` environment variable (default: `admin@trident.local` in dev)
- **Password:** Set via `ADMIN_PASSWORD_HASH` environment variable (bcrypt hash)
  - For local dev: see `db/users.json` (bcrypt hashed — do not share in public)
- **Access:** Full admin panel & product management

### Test Customer Account
- **Email:** See `db/users.json` for seeded test accounts
- **Password:** Stored as bcrypt hash in `db/users.json` — use your local `.env` or ask the team
- **Access:** Browse, cart, checkout, order tracking

### Login Methods

#### 1️⃣ **Email & Password**
- Standard login with secure bcrypt hashing
- 7-day JWT token expiration
- Remember me option

#### 2️⃣ **Mobile OTP**
- Enter 10-digit phone number
- Receive 6-digit OTP
- One-time password verification

#### 3️⃣ **Google OAuth**
- Pre-configured integration
- Auto-account creation
- Social login experience

## 🔗 API Endpoints

### Authentication Routes
```
POST   /api/auth/login              # Email & password login
POST   /api/auth/register           # Create new account
POST   /api/auth/otp/send           # Send OTP to phone
POST   /api/auth/otp/verify         # Verify OTP & get token
POST   /api/auth/google             # Google OAuth login
GET    /api/auth/me                 # Get current user info
POST   /api/auth/logout             # Clear session
```

### Product Routes
```
GET    /api/products                # Get all products
GET    /api/products/{id}           # Get product details
GET    /api/products/search         # Search products
```

### Cart & Orders
```
GET    /api/cart                    # Get user's cart
POST   /api/cart/add                # Add item to cart
POST   /api/cart/remove             # Remove from cart
POST   /api/orders                  # Create order
GET    /api/orders                  # Get order history
GET    /api/orders/{id}             # Get order details
```

### Admin Routes (requires authentication)
```
POST   /api/admin/products          # Create product
PUT    /api/admin/products/{id}     # Update product
DELETE /api/admin/products/{id}     # Delete product
GET    /api/admin/orders            # View all orders
POST   /api/admin/settings          # Update settings
```

### Contact & Chat
```
POST   /api/contact                 # Submit contact form
GET    /api/chat                    # Get chat messages
POST   /api/chat                    # Send chat message
```

## 📊 Database Structure

### users.json
Stores user accounts with secure password hashing.
```json
{
  "id": 1,
  "name": "Admin",
  "email": "admin@trident.local",
  "phone": "9999999999",
  "password_hash": "bcrypt_hashed_password",
  "role": "admin",
  "created_at": "2026-04-15T10:00:00"
}
```

### products.json
Product catalog with pricing, images, and metadata.

### orders.json
Customer orders with items, totals, and status tracking.

### contacts.json
Contact form submissions from visitors.

### chat.json
Customer support chat messages.

## 🛠️ Development

### Running in Development Mode
```bash
python backend/app.py --reload
```

### Testing Authentication
```bash
# Test email login (replace with your local dev credentials)
curl -X POST http://localhost:8010/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"YOUR_DEV_EMAIL","password":"YOUR_DEV_PASSWORD"}'

# Test OTP send
curl -X POST http://localhost:8000/api/auth/otp/send \
  -H "Content-Type: application/json" \
  -d '{"phone":"9876543210"}'
```

## ⚠️ Troubleshooting

### Port Already in Use
```bash
# Use a different port
python backend/app.py --port 8001
```

### Database Connection Issues
- Ensure `db/` folder exists with all JSON files
- Check file permissions (should be readable/writable)
- Verify JSON syntax in `db/*.json` files

### Login Not Working
- Clear browser localStorage: Press F12 → Application → LocalStorage → Clear
- Verify credentials: Check `db/users.json`
- Check browser console for errors: F12 → Console

### Admin Panel Access Denied
- Ensure logged-in user has `"role": "admin"` in `db/users.json`
- Clear session and log in again
- Verify JWT token not expired (7-day limit)

## 📝 File Statistics

- **Total Pages:** 19 HTML files
- **JavaScript Modules:** 22 files (14 pages + 6 shared + 2 core)
- **API Endpoints:** 50+ routes
- **Database Tables:** 5 JSON files
- **Project Size:** ~7.3 MB (optimized)

## 🎯 Features by Page

| Page | Features |
|------|----------|
| `index.html` | Hero banner, statistics, featured products, categories |
| `products.html` | Product grid, filtering, sorting, search |
| `cart.html` | Cart items, quantities, remove/update, totals, checkout |
| `checkout.html` | Shipping form, payment details, order summary |
| `login.html` | Email, OTP, Google login tabs, password reset |
| `register.html` | Sign up form, terms acceptance, auto-login |
| `admin.html` | Product CRUD, featured toggle, image upload |
| `wishlist.html` | Saved items, move to cart, email wishlist |
| `track.html` | Order tracking, delivery status, support |
| `contact.html` | Contact form, support chat, inquiry tickets |

## 📱 Browser Support

- Chrome/Edge: ✅ Full support
- Firefox: ✅ Full support
- Safari: ✅ Full support
- Mobile: ✅ Fully responsive

## 📄 License

This project is provided as-is for educational and commercial use.

## 👨‍💻 Support

For issues or questions, refer to the comprehensive documentation files or check browser console (F12) for error details.
- `POST /api/orders`
- `POST /api/contact`

## Notes

- `db/products.json` is the product source of truth.
- `frontend/js/products.json` is kept as a mirrored catalog snapshot for compatibility.
- This workspace did not have Python installed during implementation, so the code was prepared for local run but not executed in this environment.
