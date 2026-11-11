"""
Virtual try-on API.

The storefront's live "Fit Check" runs fully in the browser (camera + pose
detection + garment overlay) and needs no server. This router adds an
OPTIONAL photoreal AI render on top, using a hosted IDM-VTON model on
Replicate. It is disabled until REPLICATE_API_TOKEN is set.

    GET  /api/v1/tryon/status    -> {"ai_enabled": bool, "provider": str|None}
    POST /api/v1/tryon/generate  -> multipart: photo (jpg/png/webp), product_id
                                    returns {"image_url": "..."}

Cost/abuse controls: login required, 8MB photo cap, per-user rate limit.
Photos are sent to the provider and not stored by TridentWear.
"""

from __future__ import annotations

import base64
import os
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.services.auth_service import get_session_user
from app.services.product_service import load_products

router = APIRouter(prefix="/api/v1/tryon", tags=["tryon"])

IMAGES_DIR = Path(__file__).resolve().parents[3] / "frontend" / "assets" / "images"
REPLICATE_URL = "https://api.replicate.com/v1/predictions"
# cuuupid/idm-vton — override with TRYON_MODEL_VERSION if you pin a newer one
DEFAULT_MODEL_VERSION = "0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"
MAX_PHOTO_BYTES = 8 * 1024 * 1024
RATE_LIMIT = 5            # renders
RATE_WINDOW = 60 * 60     # per hour, per user
_usage: Dict[int, List[float]] = {}


def _token() -> str:
    return os.getenv("REPLICATE_API_TOKEN", "").strip()


@router.get("/status")
def tryon_status() -> Dict[str, Any]:
    enabled = bool(_token())
    return {"ai_enabled": enabled, "provider": "replicate" if enabled else None, "live_ar": True}


def _check_rate(user_id: int) -> None:
    now = time.time()
    recent = [t for t in _usage.get(user_id, []) if now - t < RATE_WINDOW]
    if len(recent) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Try-on limit reached. Please try again in an hour.")
    recent.append(now)
    _usage[user_id] = recent


def _data_uri(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _garment_data_uri(product: Dict[str, Any]) -> str:
    rel = str(product.get("image", "")).removeprefix("/images/")
    path = (IMAGES_DIR / rel).resolve()
    if IMAGES_DIR.resolve() not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Garment image not found.")
    from PIL import Image
    # flatten transparent cut-out onto white: VTON models expect an opaque garment photo
    with Image.open(path) as im:
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        buf = BytesIO()
        bg.save(buf, format="JPEG", quality=92)
    return _data_uri(buf.getvalue(), "image/jpeg")


def _call_provider(person_uri: str, garment_uri: str, description: str, category: str) -> str:
    payload = {
        "version": os.getenv("TRYON_MODEL_VERSION", DEFAULT_MODEL_VERSION),
        "input": {
            "human_img": person_uri,
            "garm_img": garment_uri,
            "garment_des": description,
            "category": category,
            "crop": False,
            "steps": 30,
        },
    }
    headers = {"Authorization": f"Bearer {_token()}", "Prefer": "wait=60"}
    try:
        with httpx.Client(timeout=90) as client:
            res = client.post(REPLICATE_URL, json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()
            deadline = time.time() + 80
            while data.get("status") in ("starting", "processing") and time.time() < deadline:
                time.sleep(2)
                res = client.get(data["urls"]["get"], headers=headers)
                res.raise_for_status()
                data = res.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Try-on provider error: {exc}") from exc
    if data.get("status") != "succeeded":
        raise HTTPException(status_code=502, detail="AI try-on did not finish. Please try again.")
    output = data.get("output")
    url = output[0] if isinstance(output, list) and output else output
    if not isinstance(url, str) or not url.startswith("http"):
        raise HTTPException(status_code=502, detail="AI try-on returned no image.")
    return url


@router.post("/generate")
async def tryon_generate(
    request: Request,
    product_id: int = Form(...),
    photo: UploadFile = File(...),
) -> Dict[str, Any]:
    if not _token():
        raise HTTPException(status_code=503, detail="AI try-on is not configured on this server.")
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in to use AI try-on.")
    _check_rate(int(user["id"]))

    raw = await photo.read(MAX_PHOTO_BYTES + 1)
    if len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="Photo must be under 8MB.")
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(BytesIO(raw)) as probe:
            fmt = (probe.format or "").upper()
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG or WEBP photo.")
    if fmt not in ("JPEG", "PNG", "WEBP"):
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG or WEBP photo.")

    product = next((p for p in load_products() if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    image_url = _call_provider(
        _data_uri(raw, f"image/{fmt.lower()}"),
        _garment_data_uri(product),
        f"{product.get('base_color', '')} {product['name']}".strip(),
        "upper_body",
    )
    return {"success": True, "image_url": image_url, "product_id": product_id}
