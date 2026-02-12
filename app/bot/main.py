import asyncio
import sys
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Root yo'lini sozlash
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from app.core.config import settings
from app.bot.handlers import common, auth, admin

async def main():
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, 
             default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Routerlarni ulash
    dp.include_router(common.router)
    dp.include_router(auth.router)
    dp.include_router(admin.router)

    print("🚀 Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())