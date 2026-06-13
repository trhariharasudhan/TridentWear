import os
import json
import sys
import argparse
from pathlib import Path
from sqlalchemy import create_engine, select, func

# Setup paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = BACKEND_DIR.parent
DB_DIR = BASE_DIR / "db"
sys.path.append(str(BACKEND_DIR))

from app.db.models import users, products, orders, chat_messages, reviews, otp_sessions, contacts, coupons
from app.core.logger import app_logger

PG_DSN = os.getenv("DATABASE_URL") or os.getenv("PG_DSN", "postgresql://user:password@localhost/tridentwear")

def load_json(filename):
    path = DB_DIR / filename
    if not path.exists():
        # Fallback to check if already archived
        archived_path = DB_DIR / f"{filename}.archive"
        if archived_path.exists():
            path = archived_path
        else:
            return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def verify(archive_json=False):
    print("=== DATA PARITY VERIFICATION ===")
    
    users_data = load_json("users.json")
    products_data = load_json("products.json")
    orders_data = load_json("orders.json")
    reviews_data = load_json("reviews.json")
    otp_data = load_json("otp_sessions.json")
    chat_data = load_json("chat.json")
    contacts_data = load_json("contacts.json")
    coupons_data = load_json("coupons.json")
    
    engine = create_engine(PG_DSN)
    
    parity = True
    
    try:
        with engine.connect() as conn:
            pg_users_count = conn.execute(select(func.count()).select_from(users)).scalar()
            print(f"Users: JSON={len(users_data)} | PG={pg_users_count}")
            if len(users_data) != pg_users_count:
                print("❌ Mismatch in Users")
                parity = False
                
            pg_products_count = conn.execute(select(func.count()).select_from(products)).scalar()
            print(f"Products: JSON={len(products_data)} | PG={pg_products_count}")
            if len(products_data) != pg_products_count:
                print("❌ Mismatch in Products")
                parity = False
                
            pg_orders_count = conn.execute(select(func.count()).select_from(orders)).scalar()
            print(f"Orders: JSON={len(orders_data)} | PG={pg_orders_count}")
            if len(orders_data) != pg_orders_count:
                print("❌ Mismatch in Orders")
                parity = False
                
            pg_chat_count = conn.execute(select(func.count()).select_from(chat_messages)).scalar()
            print(f"Chat Messages: JSON={len(chat_data)} | PG={pg_chat_count}")
            if len(chat_data) != pg_chat_count:
                print("❌ Mismatch in Chat Messages")
                parity = False

            pg_contacts_count = conn.execute(select(func.count()).select_from(contacts)).scalar()
            print(f"Contacts: JSON={len(contacts_data)} | PG={pg_contacts_count}")
            if len(contacts_data) != pg_contacts_count:
                print("❌ Mismatch in Contacts")
                parity = False

            pg_reviews_count = conn.execute(select(func.count()).select_from(reviews)).scalar()
            print(f"Reviews: JSON={len(reviews_data)} | PG={pg_reviews_count}")
            if len(reviews_data) != pg_reviews_count:
                print("❌ Mismatch in Reviews")
                parity = False

            pg_otp_count = conn.execute(select(func.count()).select_from(otp_sessions)).scalar()
            print(f"OTP Sessions: JSON={len(otp_data)} | PG={pg_otp_count}")
            if len(otp_data) != pg_otp_count:
                print("❌ Mismatch in OTP Sessions")
                parity = False

            pg_coupons_count = conn.execute(select(func.count()).select_from(coupons)).scalar()
            print(f"Coupons: JSON={len(coupons_data)} | PG={pg_coupons_count}")
            if len(coupons_data) != pg_coupons_count:
                print("❌ Mismatch in Coupons")
                parity = False
    except Exception as e:
        print(f"❌ Verification failed due to database connection error: {e}")
        parity = False
 
    if parity:
        print("\nAll records migrated successfully.")
        if not archive_json:
            print("JSON files left untouched. Pass --archive-json after backups to rename them.")
            print("\nMIGRATION SAFE: TRUE")
            return
        print("Archiving JSON files...")
        
        # Archiving logic - renaming, never deleting
        for fname in ["users.json", "products.json", "orders.json", "contacts.json", "chat.json", "reviews.json", "otp_sessions.json", "coupons.json"]:
            fpath = DB_DIR / fname
            if fpath.exists():
                fpath.rename(DB_DIR / f"{fname}.archive")
                print(f" -> Archived {fname} to {fname}.archive")
                
        print("\nMIGRATION SAFE: TRUE")
    else:
        print("\nMIGRATION SAFE: FALSE")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-json", action="store_true", help="Rename JSON files only after manual backup confirmation.")
    args = parser.parse_args()
    verify(archive_json=args.archive_json)
