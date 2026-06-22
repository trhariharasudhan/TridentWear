from typing import Dict, Any, List
from app.core.db_switch import db
from app.services.order_service import load_orders

def get_analytics_data() -> Dict[str, Any]:
    orders = load_orders()
    products = db.read("products", {})
    
    # Orders metrics
    total_orders = len(orders)
    total_revenue = sum(o.get("subtotal", 0) for o in orders)
    unique_customers = len(set(o.get("customer", {}).get("email") for o in orders if o.get("customer", {}).get("email")))
    
    average_order_value = 0.0
    if total_orders > 0:
        average_order_value = round(total_revenue / total_orders, 2)
        
    product_sales = {}
    for o in orders:
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
        "low_stock_list": low_stock_list
    }
