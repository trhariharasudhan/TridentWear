from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path
import jwt
import os

router = APIRouter(tags=["frontend"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
FRONTEND_ROOT = BASE_DIR / "frontend"

# ── Minimal server-side admin guard ───────────────────────────────────────────
def _is_admin(request: Request) -> bool:
    """Return True if the request carries a valid admin JWT or session marker.
    This is a defence-in-depth check — JS also guards on the client side.
    """
    try:
        from app.services.auth_service import get_session_user
        user = get_session_user(request)
        return bool(user and user.get("role") == "admin")
    except Exception:
        return False

def _load_component(name: str) -> str:
    comp_path = FRONTEND_ROOT / "components" / f"{name}.html"
    try:
        return comp_path.read_text(encoding="utf-8")
    except OSError:
        return ""

def html_response(filename: str) -> HTMLResponse:
    file_paths = [
        FRONTEND_ROOT / filename,
        FRONTEND_ROOT / "pages" / filename,
        FRONTEND_ROOT / "pages" / "shop" / filename,
        FRONTEND_ROOT / "pages" / "account" / filename,
        FRONTEND_ROOT / "pages" / "info" / filename,
        FRONTEND_ROOT / "pages" / "admin" / filename,
        FRONTEND_ROOT / "pages" / "legal" / filename,
        FRONTEND_ROOT / "pages" / "support" / filename,
        FRONTEND_ROOT / "pages" / "error" / filename,
    ]
    for path in file_paths:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            if "{{ component:header }}" in content:
                content = content.replace("{{ component:header }}", _load_component("header"))
            if "{{ component:footer }}" in content:
                content = content.replace("{{ component:footer }}", _load_component("footer"))
            return HTMLResponse(content=content)
    
    error_path = FRONTEND_ROOT / "pages" / "error" / "404.html"
    if error_path.exists():
        content = error_path.read_text(encoding="utf-8")
        if "{{ component:header }}" in content:
            content = content.replace("{{ component:header }}", _load_component("header"))
        if "{{ component:footer }}" in content:
            content = content.replace("{{ component:footer }}", _load_component("footer"))
        return HTMLResponse(content=content, status_code=404)
    return HTMLResponse(content="<h1>404 Not Found</h1>", status_code=404)

@router.get("/")
def serve_home(): return html_response("index.html")

@router.get("/products")
def serve_products_page(): return html_response("products.html")

@router.get("/cart")
def serve_cart_page(): return html_response("cart.html")

@router.get("/product")
def serve_product_page(): return html_response("product.html")

@router.get("/checkout")
def serve_checkout_page(): return html_response("checkout.html")

@router.get("/auth")
def serve_auth_page(request: Request): return RedirectResponse(url="/login")

@router.get("/login")
def serve_login_page(): return html_response("login.html")

@router.get("/register")
def serve_register_page(): return html_response("register.html")

@router.get("/about")
def serve_about_page(): return html_response("about.html")

@router.get("/contact")
def serve_contact_page(): return html_response("contact.html")

@router.get("/admin")
def serve_admin_page(request: Request):
    if not _is_admin(request):
        return RedirectResponse(url="/login?next=%2Fadmin", status_code=302)
    return html_response("admin.html")

@router.get("/admin/chat")
def serve_admin_chat_page(request: Request):
    if not _is_admin(request):
        return RedirectResponse(url="/login?next=%2Fadmin", status_code=302)
    return html_response("chat.html")

@router.get("/wishlist")
def serve_wishlist_page(): return html_response("wishlist.html")

@router.get("/privacy")
def serve_privacy_page(): return html_response("privacy.html")

@router.get("/terms")
def serve_terms_page(): return html_response("terms.html")

@router.get("/returns")
def serve_returns_page(): return html_response("returns.html")

@router.get("/shipping")
def serve_shipping_page(): return html_response("shipping.html")

@router.get("/track")
def serve_track_page(): return html_response("track.html")

@router.get("/chat")
def serve_chat_page():
    # Explicitly serve support chat — NOT admin/chat.html (which shares the filename)
    support_chat = FRONTEND_ROOT / "pages" / "support" / "chat.html"
    if support_chat.exists():
        content = support_chat.read_text(encoding="utf-8")
        if "{{ component:header }}" in content:
            content = content.replace("{{ component:header }}", _load_component("header"))
        if "{{ component:footer }}" in content:
            content = content.replace("{{ component:footer }}", _load_component("footer"))
        return HTMLResponse(content=content)
    return html_response("chat.html")

@router.get("/profile")
def serve_profile_page(): return html_response("profile.html")

@router.get("/profile-setup")
def serve_profile_setup_page(): return html_response("profile-setup.html")

@router.get("/verify")
def serve_verify_page(): return html_response("verify.html")

@router.get("/{page_name}.html")
def legacy_html_routes(page_name: str, request: Request):
    return html_response(f"{page_name}.html")
