"""Public storefront settings + admin editor endpoint."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.services.audit_service import log_action
from app.services.auth_service import require_admin
from app.services.site_service import get_site, update_site

router = APIRouter(tags=["site"])


@router.get("/api/v1/site")
def site(response: Response) -> Dict[str, Any]:
    # no-cache: an admin who just saved must see it on the next load. The storefront keeps its own
    # 60 s per-tab copy (sessionStorage) and clears it after a save.
    response.headers["Cache-Control"] = "no-cache"
    return {"site": get_site()}


class SitePayload(BaseModel):
    announcements: Optional[List[str]] = None
    hero_line: Optional[str] = None
    hero_text: Optional[str] = None
    drop_title: Optional[str] = None
    rail: Optional[List[int]] = None
    drop: Optional[List[int]] = None
    contact: Optional[Dict[str, Any]] = None


@router.put("/api/v1/admin/site")
def save_site(payload: SitePayload, request: Request, admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    result = update_site(payload.model_dump(exclude_none=True))
    log_action(admin.get("id"), "update", "site_settings", "storefront", result["before"], result["after"], request)
    return {"success": True, "message": "Storefront updated.", "site": result["after"]}
