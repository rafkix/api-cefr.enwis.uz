from aiogram import Router

from app.bot.handlers.start import router as start_router
from app.bot.handlers.auth import router as auth_router
from app.bot.handlers.admin import router as admin_router


def setup_routers() -> Router:
    router = Router()
    router.include_router(start_router)
    router.include_router(auth_router)
    router.include_router(admin_router)
    return router