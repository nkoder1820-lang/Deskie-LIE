"""Runtime-togglable app settings (no .env editing / restart needed)."""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app import runtime_settings

router = APIRouter(prefix="/api/settings", tags=["Settings"])


def _current() -> dict:
    return {
        "enable_serpapi_enricher": bool(
            runtime_settings.get("ENABLE_SERPAPI_ENRICHER", settings.ENABLE_SERPAPI_ENRICHER)
        ),
        "serpapi_configured": bool(settings.SERPAPI_KEY),
        "adzuna_configured": bool(settings.ADZUNA_APP_ID and settings.ADZUNA_APP_KEY),
    }


@router.get("")
def get_settings():
    return _current()


class SettingsPatch(BaseModel):
    enable_serpapi_enricher: Optional[bool] = None


@router.patch("")
def patch_settings(req: SettingsPatch):
    """Applies immediately to subsequent research runs and persists across
    restarts (runtime_settings.json overrides the .env default)."""
    if req.enable_serpapi_enricher is not None:
        runtime_settings.set_value("ENABLE_SERPAPI_ENRICHER", bool(req.enable_serpapi_enricher))
    return _current()
