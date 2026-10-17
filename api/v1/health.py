from fastapi import APIRouter

from core.config import get_settings

router = APIRouter(tags=["ops"])


@router.get("/health", summary="健康检查")
async def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "app": "SmartQA", "env": settings.app_env}
