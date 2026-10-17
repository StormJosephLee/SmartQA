from fastapi import APIRouter

from api.v1 import admin, auth, chat, health, knowledge

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(knowledge.router)
api_router.include_router(admin.router)
