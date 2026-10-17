"""SmartQA 服务入口：uvicorn main:app"""

from __future__ import annotations

from fastapi import FastAPI

from api.v1.router import api_router
from core.config import get_settings
from core.logging import setup_logging
from core.middleware import TraceIdMiddleware, register_exception_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="SmartQA",
        version="0.1.0",
        description="企业级智能问答助手（RAG + Agent）",
    )
    app.add_middleware(TraceIdMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["ops"], summary="健康检查（根别名）")
    async def root_health() -> dict:
        return {"status": "ok", "app": "SmartQA", "env": settings.app_env}

    return app


app = create_app()
