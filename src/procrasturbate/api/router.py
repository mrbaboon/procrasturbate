"""Main API router aggregation."""

from fastapi import APIRouter

from .admin import router as admin_router
from .health import router as health_router
from .ui import router as ui_router
from .webhooks import router as webhooks_router

router = APIRouter()

# Include sub-routers
router.include_router(health_router)
router.include_router(webhooks_router)
router.include_router(admin_router)
router.include_router(ui_router)
