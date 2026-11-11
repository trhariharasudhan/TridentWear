from typing import Dict, Any, List
from app.core.db_switch import db
from app.services.order_service import load_orders

def get_analytics_data() -> Dict[str, Any]:
    orders = load_orders()
    products = db.read("products", {})
    
    # Orders metrics — revenue only counts real sales: paid online orders or
    # cash-on-delivery orders that were not cancelled. Pending/abandoned
    # Razorpay attempts and cancellations are excluded.
    def _is_sale(o: Dict[str, Any]) -> bool:
        if str(o.get("status", "")).lower() == "cancelled":
            return False
        return str(o.get("payment_status", "")).lower() in ("paid", "cod_pending", "cod_collected")

    def _amount(o: Dict[str, Any]) -> float:
        try:
            return float(o.get("total", o.get("subtotal", 0)) or 0)
        except (TypeError, ValueError):
            return 0.0

    sales = [o for o in orders if _is_sale(o)]
    total_orders = len(orders)
    total_revenue = sum(_amount(o) for o in sales)

    from collections import Counter
    from datetime import datetime, timedelta, timezone
    status_breakdown = dict(Counter(str(o.get("status", "unknown")).lower() for o in orders))
    today = datetime.now(timezone.utc).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    by_day = {d: {"date": d, "revenue": 0.0, "orders": 0} for d in days}
    for o in sales:
        d = str(o.get("created_at", ""))[:10]
        if d in by_day:
            by_day[d]["revenue"] += _amount(o)
            by_day[d]["orders"] += 1
    unique_customers = len(set(o.get("customer", {}).get("email") for o in orders if o.get("customer", {}).get("email")))
    
    average_order_value = 0.0
    if sales:
        average_order_value = round(total_revenue / len(sales), 2)
        
    product_sales = {}
    for o in sales:
        for item in o.get("items", []):
            name = item.get("name")
            qty = item.get("qty", 1)
            if name:
                product_sales[name] = product_sales.get(name, 0) + qty
                
    top_products = [{"name": k, "sold": v} for k, v in sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:5]]
    
    # Products / Inventory metrics
    total_products = len(products)
    total_stock_units = 0
    low_stock_count = 0
    out_of_stock_count = 0
    featured_count = 0
    inventory_value = 0.0
    low_stock_list = []
    
    for p in products:
        stock = int(p.get("stock", 0))
        price = float(p.get("price", 0.0))
        is_featured = bool(p.get("featured", False))
        
        total_stock_units += stock
        inventory_value += (price * stock)
        
        if is_featured:
            featured_count += 1
            
        if stock == 0:
            out_of_stock_count += 1
            low_stock_count += 1
            low_stock_list.append({
                "name": p.get("name"),
                "category": p.get("category"),
                "stock": stock
            })
        elif stock <= 10:
            low_stock_count += 1
            low_stock_list.append({
                "name": p.get("name"),
                "category": p.get("category"),
                "stock": stock
            })
            
    return {
        "total_orders": total_orders,
        "total_revenue": round(total_revenue, 2),
        "customers": unique_customers,
        "top_products": top_products,
        
        "total_products": total_products,
        "total_stock_units": total_stock_units,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "featured_count": featured_count,
        "inventory_value": round(inventory_value, 2),
        "average_order_value": average_order_value,
        "low_stock_list": low_stock_list,
        "paid_orders": len(sales),
        "status_breakdown": status_breakdown,
        "revenue_by_day": [dict(v, revenue=round(v["revenue"], 2)) for v in by_day.values()],
    }
