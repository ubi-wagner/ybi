from fastapi import APIRouter
from app.db import one
from app.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    try:
        one("SELECT 1 AS ok")
        db = "up"
    except Exception as e:  # Railway healthcheck should fail loudly, not silently
        db = f"down: {e.__class__.__name__}"
    return {"status": "ok" if db == "up" else "degraded",
            "database": db, "period": settings.period, "env": settings.env}
