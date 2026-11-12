"""Storefront settings the admin can edit without a deploy.

Stored as one row in `site_settings` (key='storefront', value=JSON). Every field is
validated and clipped here; the storefront still escapes everything it renders.
"""
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import HTTPException

from app.core.db_switch import db

KEY = "storefront"
DEFAULTS: Dict[str, Any] = {
    "announcements": [
        "Free shipping on every order across India",
        "Use code TRIDENTFIRST for 20% off your first order",
        "7-day exchanges, no questions asked",
        "See it on you first with AI Fit Check",
    ],
    "hero_line": "Heavyweight tees // Oxford shirts // Linen camp shirts // Made in India",
    "hero_text": "240 GSM tees and cotton shirts with a small gold Trident. Try anything on with your camera first.",
    "rail": [],          # product ids, in hanging order; empty = the default curated rail
    "drop_title": "Drop 01 is live",
    "drop": [],          # up to 4 product ids for the home page grid; empty = default picks
    "contact": {
        "email": "hello@tridentwear.in",
        "phone": "+91 90000 00000",
        "whatsapp": "919000000000",
        "address": "TridentWear Studio, BTM Layout, Bengaluru, Karnataka 560076",
        "instagram": "https://instagram.com/tridentwear",
    },
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _row() -> Dict[str, Any]:
    rows = db.read("site_settings", {"key": KEY})
    return rows[0] if rows else {}


def get_site() -> Dict[str, Any]:
    stored = _row().get("value") or {}
    out = {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}
    out["contact"] = {**DEFAULTS["contact"], **(stored.get("contact") or {})}
    return out


def _text(v: Any, n: int, field: str, required: bool = True) -> str:
    s = re.sub(r"\s+", " ", str(v or "")).strip()
    if required and not s:
        raise HTTPException(status_code=400, detail=f"{field} can't be empty.")
    return s[:n]


def _ids(v: Any, limit: int, field: str) -> List[int]:
    if not isinstance(v, list):
        raise HTTPException(status_code=400, detail=f"{field} must be a list of products.")
    known = {int(p["id"]) for p in db.read("products", {}) if p.get("id") is not None}
    out: List[int] = []
    for x in v:
        try:
            i = int(x)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{field}: {x!r} is not a product id.")
        if i not in known:
            raise HTTPException(status_code=400, detail=f"{field}: product {i} doesn't exist.")
        if i not in out:
            out.append(i)
    if len(out) > limit:
        raise HTTPException(status_code=400, detail=f"{field}: pick at most {limit} products.")
    return out


def update_site(payload: Dict[str, Any]) -> Dict[str, Any]:
    cur = get_site()
    nxt = dict(cur)
    if "announcements" in payload:
        items = [_text(a, 120, "Announcement") for a in (payload["announcements"] or []) if str(a or "").strip()]
        if not 1 <= len(items) <= 6:
            raise HTTPException(status_code=400, detail="Add between 1 and 6 announcements.")
        nxt["announcements"] = items
    if "hero_line" in payload:
        nxt["hero_line"] = _text(payload["hero_line"], 140, "Hero top line")
    if "hero_text" in payload:
        nxt["hero_text"] = _text(payload["hero_text"], 220, "Hero description")
    if "drop_title" in payload:
        nxt["drop_title"] = _text(payload["drop_title"], 60, "Drop title")
    if "rail" in payload:
        rail = _ids(payload["rail"], 24, "Rail")
        if rail and len(rail) < 4:
            raise HTTPException(status_code=400, detail="Hang at least 4 pieces on the rail, or leave it empty for the default.")
        nxt["rail"] = rail
    if "drop" in payload:
        nxt["drop"] = _ids(payload["drop"], 4, "Drop")
    if "contact" in payload:
        c = {**cur["contact"], **{k: v for k, v in (payload["contact"] or {}).items() if k in DEFAULTS["contact"]}}
        c = {k: _text(v, 200, k.capitalize(), required=False) for k, v in c.items()}
        if c["email"] and not EMAIL_RE.match(c["email"]):
            raise HTTPException(status_code=400, detail="Enter a valid contact email.")
        if c["whatsapp"] and not re.fullmatch(r"\d{10,15}", c["whatsapp"]):
            raise HTTPException(status_code=400, detail="WhatsApp number: digits only, with country code (e.g. 919876543210).")
        if c["instagram"] and not c["instagram"].startswith("https://"):
            raise HTTPException(status_code=400, detail="Instagram link must start with https://")
        nxt["contact"] = c

    now = datetime.now(timezone.utc).isoformat()
    if _row():
        db.update("site_settings", {"key": KEY}, {"value": nxt, "updated_at": now})
    else:
        db.insert("site_settings", {"key": KEY, "value": nxt, "updated_at": now})
    return {"before": cur, "after": nxt}
