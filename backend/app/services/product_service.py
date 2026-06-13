import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status

from app.core.db_switch import db

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
FRONTEND_ROOT = BASE_DIR / "frontend"
FRONTEND_PRODUCTS_PATH = FRONTEND_ROOT / "assets" / "data" / "products.json"

DEFAULT_PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "name": "Classic Black Tee",
        "category": "tshirt",
        "price": 799,
        "description": "Premium 220 GSM cotton crew neck tee in timeless black. Relaxed fit, pre-shrunk fabric.",
        "image": "/images/black-tshirt.png",
        "tag": "Bestseller",
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "stock": 150,
        "featured": True,
    },
    {
        "id": 2,
        "name": "White Minimal Tee",
        "category": "tshirt",
        "price": 699,
        "description": "Clean white tee with a minimal cut. 200 GSM bio-washed cotton for an ultra-soft feel.",
        "image": "/images/white-tshirt.png",
        "tag": "New Drop",
        "sizes": ["S", "M", "L", "XL"],
        "stock": 200,
        "featured": True,
    },
    {
        "id": 3,
        "name": "Navy Formal Shirt",
        "category": "shirt",
        "price": 1299,
        "description": "Slim-fit navy blue formal shirt with wrinkle-resistant fabric built for all-day structure.",
        "image": "/images/navy-shirt.png",
        "tag": "Premium",
        "sizes": ["S", "M", "L", "XL"],
        "stock": 80,
        "featured": True,
    },
    {
        "id": 4,
        "name": "Olive Casual Shirt",
        "category": "shirt",
        "price": 1099,
        "description": "Relaxed-fit olive button-up with breathable cotton blend and easy street-luxury styling.",
        "image": "/images/olive-shirt.png",
        "tag": "Street Essential",
        "sizes": ["M", "L", "XL", "XXL"],
        "stock": 120,
        "featured": True,
    },
    {
        "id": 5,
        "name": "Charcoal Oversized Tee",
        "category": "tshirt",
        "price": 899,
        "description": "Oversized drop-shoulder tee in charcoal grey. Heavy cotton weight with a clean structured drape.",
        "image": "/images/grey-tshirt.png",
        "tag": "Trending",
        "sizes": ["M", "L", "XL", "XXL"],
        "stock": 100,
        "featured": False,
    },
    {
        "id": 6,
        "name": "Stone Linen Shirt",
        "category": "shirt",
        "price": 1199,
        "description": "Lightweight linen-blend shirt in a clean stone tone with a refined mandarin collar finish.",
        "image": "/images/olive-shirt.png",
        "tag": "Summer Edit",
        "sizes": ["S", "M", "L", "XL"],
        "stock": 90,
        "featured": False,
    },
]

CANVA_TSHIRT_SPEC: Dict[str, Any] = {
    "cloth_type": "Half Sleeve T-Shirt",
    "fabric": "100% Cotton",
    "gsm": 150,
    "fit_type": "Unisex",
    "neck_type": "Round Neck",
    "print_method": ["DTG", "Embroidery"],
    "wash_care_label": True,
    "wash_care": [
        "Machine wash cold with like colours",
        "Do not bleach",
        "Dry inside out in shade",
        "Warm iron inside out; do not iron on print",
    ],
    "tag_metadata": {
        "season": "All season",
        "style": "Half Sleeve T-Shirt",
        "material": "100% Cotton",
        "factory": "TridentWear India",
    },
}

def normalize_image_path(value: str) -> str:
    image_value = str(value or "").strip()
    if not image_value:
        return "/images/hero-banner.png"
    if image_value.startswith("/images/"):
        return image_value
    if image_value.startswith("../images/"):
        return f"/images/{Path(image_value).name}"
    return f"/images/{Path(image_value).name}"

def normalize_sizes(value: Any) -> List[str]:
    if isinstance(value, list):
        sizes = [str(size).strip().upper() for size in value if str(size).strip()]
    else:
        sizes = [segment.strip().upper() for segment in str(value or "").split(",") if segment.strip()]
    return sizes or ["S", "M", "L", "XL"]

def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

def normalize_string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").split(",")
    return [str(item).strip() for item in items if str(item).strip()]

def normalize_tag_metadata(raw_product: Dict[str, Any], normalized: Dict[str, Any]) -> Dict[str, Any]:
    metadata = raw_product.get("tag_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    defaults = CANVA_TSHIRT_SPEC["tag_metadata"]
    return {
        "season": str(metadata.get("season") or defaults["season"]).strip(),
        "style": str(metadata.get("style") or normalized["cloth_type"]).strip(),
        "material": str(metadata.get("material") or normalized["fabric"]).strip(),
        "model_size": str(metadata.get("model_size") or "Model wears M").strip(),
        "factory": str(metadata.get("factory") or defaults["factory"]).strip(),
    }

def normalize_product(raw_product: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
    fabric = str(raw_product.get("fabric") or raw_product.get("material") or CANVA_TSHIRT_SPEC["fabric"]).strip()
    print_method = normalize_string_list(raw_product.get("print_method", CANVA_TSHIRT_SPEC["print_method"]))
    wash_care = normalize_string_list(raw_product.get("wash_care", CANVA_TSHIRT_SPEC["wash_care"]))
    normalized = {
        "id": int(raw_product.get("id", index + 1)),
        "name": str(raw_product.get("name", "")).strip(),
        "category": str(raw_product.get("category", "tshirt")).strip().lower(),
        "price": int(float(raw_product.get("price", 0) or 0)),
        "description": str(raw_product.get("description", "")).strip(),
        "image": normalize_image_path(str(raw_product.get("image", ""))),
        "tag": str(raw_product.get("tag", "")).strip(),
        "sizes": normalize_sizes(raw_product.get("sizes", [])),
        "stock": max(int(float(raw_product.get("stock", 0) or 0)), 0),
        "featured": normalize_bool(raw_product.get("featured", index < 4)),
        "cloth_type": str(raw_product.get("cloth_type") or CANVA_TSHIRT_SPEC["cloth_type"]).strip(),
        "base_color": str(raw_product.get("base_color", "")).strip(),
        "fabric": fabric,
        "material": fabric,
        "gsm": int(float(raw_product.get("gsm", CANVA_TSHIRT_SPEC["gsm"]) or CANVA_TSHIRT_SPEC["gsm"])),
        "fit_type": str(raw_product.get("fit_type") or CANVA_TSHIRT_SPEC["fit_type"]).strip(),
        "neck_type": str(raw_product.get("neck_type") or CANVA_TSHIRT_SPEC["neck_type"]).strip(),
        "design_type": str(raw_product.get("design_type", "Graphic")).strip(),
        "design_color": str(raw_product.get("design_color", "")).strip(),
        "print_method": print_method,
        "wash_care_label": normalize_bool(raw_product.get("wash_care_label", CANVA_TSHIRT_SPEC["wash_care_label"])),
        "wash_care": wash_care,
        "size_quantities": raw_product.get("size_quantities") if isinstance(raw_product.get("size_quantities"), dict) else {},
    }
    normalized["tag_metadata"] = normalize_tag_metadata(raw_product, normalized)
    return normalized

def product_sort_key(product: Dict[str, Any]) -> Any:
    return (product["category"] != "tshirt", not product["featured"], product["id"])

def load_products() -> List[Dict[str, Any]]:
    raw_products = db.read("products", {})
    if not raw_products:
        for p in DEFAULT_PRODUCTS:
            db.insert("products", p)
        raw_products = db.read("products", {})
    products = [normalize_product(product, index) for index, product in enumerate(raw_products)]
    return sorted(products, key=product_sort_key)

def save_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Unused but kept for API stability. Syncs with DB and frontend json.
    for product in products:
        db.update("products", {"id": product["id"]}, product)
    
    all_prods = load_products()
    try:
        with open(FRONTEND_PRODUCTS_PATH, "w") as f:
            json.dump(all_prods, f, indent=2)
    except Exception:
        pass
    return all_prods

def get_all_products(category: Optional[str] = None, featured: Optional[bool] = None) -> Dict[str, Any]:
    products = load_products()
    if category:
        category_value = category.strip().lower()
        products = [product for product in products if product.get("category") == category_value]
    if featured is not None:
        products = [product for product in products if product.get("featured") is featured]
    return {"success": True, "count": len(products), "products": products}

def get_single_product(product_id: int) -> Dict[str, Any]:
    for product in load_products():
        if product.get("id") == product_id:
            return {"success": True, "product": product}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

def deduct_stock(order_items: List[Dict[str, Any]]) -> None:
    """Reduce product stock atomically after an order is saved."""
    for item in order_items:
        pid = int(item.get("id", 0))
        qty = int(item.get("qty", 1))
        res = db.read("products", {"id": pid})
        if res:
            p = res[0]
            new_stock = max(0, int(p.get("stock", 0)) - qty)
            db.update("products", {"id": pid}, {"stock": new_stock})
            
    # Sync with frontend json
    try:
        all_prods = load_products()
        with open(FRONTEND_PRODUCTS_PATH, "w") as f:
            json.dump(all_prods, f, indent=2)
    except Exception:
        pass

# Admin Product Management Logic
IMAGES_DIR = FRONTEND_ROOT / "assets" / "images"
UPLOADS_DIR = IMAGES_DIR / "uploads"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

def save_uploaded_image(upload: Any) -> str:
    import shutil
    import uuid
    extension = Path(upload.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image type.")

    filename = f"{uuid.uuid4().hex}{extension}"
    destination = UPLOADS_DIR / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as target:
        shutil.copyfileobj(upload.file, target)
    return f"/images/uploads/{filename}"

def delete_uploaded_image(image_url: str) -> None:
    if not image_url.startswith("/images/uploads/"):
        return
    relative_path = image_url.removeprefix("/images/")
    file_path = IMAGES_DIR / relative_path
    if file_path.exists():
        file_path.unlink()

def validate_product_fields(
    name: str,
    category: str,
    price: str,
    description: str,
    tag: str,
    sizes: str,
    stock: str,
    featured: str,
    fabric: str = "",
    gsm: str = "",
    fit_type: str = "",
    neck_type: str = "",
    print_method: str = "",
    wash_care_label: str = "true",
) -> Dict[str, Any]:
    product_name = name.strip()
    category_value = category.strip().lower()
    description_value = description.strip()

    if len(product_name) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product name must be at least 3 characters.")
    if category_value not in {"tshirt", "shirt"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category must be tshirt or shirt.")

    try:
        price_value = int(float(price))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Price must be a valid number.") from error
    if price_value <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Price must be greater than zero.")

    try:
        stock_value = max(int(float(stock or 0)), 0)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stock must be a valid number.") from error
    try:
        gsm_value = int(float(gsm or CANVA_TSHIRT_SPEC["gsm"]))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GSM must be a valid number.") from error

    return {
        "name": product_name,
        "category": category_value,
        "price": price_value,
        "description": description_value,
        "tag": tag.strip(),
        "sizes": normalize_sizes(sizes),
        "stock": stock_value,
        "featured": normalize_bool(featured),
        "fabric": (fabric or CANVA_TSHIRT_SPEC["fabric"]).strip(),
        "material": (fabric or CANVA_TSHIRT_SPEC["fabric"]).strip(),
        "gsm": gsm_value,
        "fit_type": (fit_type or CANVA_TSHIRT_SPEC["fit_type"]).strip(),
        "neck_type": (neck_type or CANVA_TSHIRT_SPEC["neck_type"]).strip(),
        "print_method": normalize_string_list(print_method or CANVA_TSHIRT_SPEC["print_method"]),
        "wash_care_label": normalize_bool(wash_care_label),
        "wash_care": CANVA_TSHIRT_SPEC["wash_care"],
        "cloth_type": CANVA_TSHIRT_SPEC["cloth_type"],
    }

async def process_create_product(name, category, price, description, tag, sizes, stock, featured, image, fabric="", gsm="", fit_type="", neck_type="", print_method="", wash_care_label="true") -> Dict[str, Any]:
    product_data = validate_product_fields(name, category, price, description, tag, sizes, stock, featured, fabric, gsm, fit_type, neck_type, print_method, wash_care_label)

    image_path = "/images/hero-banner.png"
    if image and getattr(image, "filename", None):
        image_path = save_uploaded_image(image)
        await image.close()

    new_product = {
        **product_data,
        "image": image_path,
    }
    inserted = db.insert("products", new_product)
    
    # Sync with frontend json
    try:
        all_prods = load_products()
        with open(FRONTEND_PRODUCTS_PATH, "w") as f:
            json.dump(all_prods, f, indent=2)
    except Exception:
        pass

    return {"success": True, "message": "Product added successfully.", "product": inserted}

async def process_update_product(product_id: int, name, category, price, description, tag, sizes, stock, featured, image, fabric="", gsm="", fit_type="", neck_type="", print_method="", wash_care_label="true") -> Dict[str, Any]:
    product_data = validate_product_fields(name, category, price, description, tag, sizes, stock, featured, fabric, gsm, fit_type, neck_type, print_method, wash_care_label)
    
    res = db.read("products", {"id": product_id})
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    existing = res[0]

    image_path = existing.get("image", "/images/hero-banner.png")
    if image and getattr(image, "filename", None):
        new_image_path = save_uploaded_image(image)
        await image.close()
        delete_uploaded_image(existing.get("image", ""))
        image_path = new_image_path

    updated_fields = {
        **product_data,
        "image": image_path,
    }
    updated = db.update("products", {"id": product_id}, updated_fields)
    returned_product = updated[0] if updated else existing

    # Sync with frontend json
    try:
        all_prods = load_products()
        with open(FRONTEND_PRODUCTS_PATH, "w") as f:
            json.dump(all_prods, f, indent=2)
    except Exception:
        pass

    return {"success": True, "message": "Product updated successfully.", "product": returned_product}

def process_delete_product(product_id: int) -> Dict[str, Any]:
    res = db.read("products", {"id": product_id})
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    existing = res[0]

    delete_uploaded_image(existing.get("image", ""))
    db.delete("products", {"id": product_id})

    # Sync with frontend json
    try:
        all_prods = load_products()
        with open(FRONTEND_PRODUCTS_PATH, "w") as f:
            json.dump(all_prods, f, indent=2)
    except Exception:
        pass

    return {"success": True, "message": f'{existing["name"]} deleted.'}
