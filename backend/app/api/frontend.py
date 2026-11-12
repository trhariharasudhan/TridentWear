"""
Serves the static storefront when the backend hosts the frontend (local dev,
Docker, Render/Railway). On GitHub Pages the same files are served statically.

New pages are flat `*.html` files in /frontend. Old pretty URLs from the
previous frontend redirect to their new equivalents so existing links work.
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse

router = APIRouter(tags=["frontend"])
FRONTEND_ROOT = Path(__file__).resolve().parents[3] / "frontend"

PAGES = {
    "index", "shop", "product", "tryon", "cart", "checkout", "order", "account",
    "wishlist", "admin", "about", "contact", "faq", "policies", "offline", "404",
}

LEGACY_REDIRECTS = {
    "/products": "/shop.html",
    "/product": "/product.html",
    "/cart": "/cart.html",
    "/checkout": "/checkout.html",
    "/login": "/account.html",
    "/auth": "/account.html",
    "/register": "/account.html#register",
    "/profile": "/account.html",
    "/wishlist": "/wishlist.html",
    "/about": "/about.html",
    "/faq": "/faq.html",
    "/contact": "/contact.html",
    "/track": "/order.html",
    "/privacy": "/policies.html#privacy",
    "/terms": "/policies.html#terms",
    "/returns": "/policies.html#returns",
    "/shipping": "/policies.html#shipping",
    "/admin": "/admin.html",
    "/tryon": "/tryon.html",
    "/fit-check": "/tryon.html",
}


def _page(name: str, status_code: int = 200) -> HTMLResponse:
    path = FRONTEND_ROOT / f"{name}.html"
    if not path.exists():
        path, status_code = FRONTEND_ROOT / "404.html", 404
    return HTMLResponse(path.read_text(encoding="utf-8"), status_code=status_code)


@router.get("/")
def home() -> HTMLResponse:
    return _page("index")


@router.get("/sw.js")
def service_worker() -> FileResponse:
    # must be served from the root so its scope covers the whole site
    return FileResponse(FRONTEND_ROOT / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@router.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(FRONTEND_ROOT / "manifest.webmanifest", media_type="application/manifest+json")


@router.get("/robots.txt")
def robots() -> PlainTextResponse:
    return PlainTextResponse((FRONTEND_ROOT / "robots.txt").read_text(encoding="utf-8"))


@router.get("/sitemap.xml")
def sitemap() -> FileResponse:
    return FileResponse(FRONTEND_ROOT / "sitemap.xml", media_type="application/xml")


@router.get("/{page}.html")
def html_page(page: str) -> HTMLResponse:
    if page not in PAGES:
        return _page("404", 404)
    return _page(page)


@router.get("/{legacy:path}")
def legacy(legacy: str, request: Request):
    target = LEGACY_REDIRECTS.get("/" + legacy.rstrip("/"))
    if target:
        qs = request.url.query
        return RedirectResponse(url=target + (("?" + qs) if qs and "#" not in target else ""), status_code=301)
    return _page("404", 404)
