from fastapi import APIRouter
from app.core.db_switch import db

router = APIRouter(prefix="/api/v1/health", tags=["health"])

@router.get("")
def health_check():
    db_status = "healthy"
    try:
        # Check storage/database health by performing a lightweight read
        db.read("products", {"id": 1})
    except Exception as e:
        db_status = f"unhealthy: {e}"
        
    return {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "service": "TridentWear API",
        "storage": db_status
    }

root_health_router = APIRouter(tags=["health"])

@root_health_router.get("/health")
def root_health_check():
    return health_check()
