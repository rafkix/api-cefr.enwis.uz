from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from app.core.config import settings

async def send_telegram_message(chat_id: str, message: str) -> bool:
    """
    Backend API dan turib Telegramga xabar yuborish funksiyasi.
    Bu funksiya vaqtincha Bot sessiyasini ochadi va xabarni yuborib yopadi.
    """
    # Bot obyektini yaratamiz
    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    try:
        # Xabarni yuborish
        await bot.send_message(chat_id=chat_id, text=message)
        return True
    except Exception as e:
        print(f"⚠️ Telegramga yuborishda xatolik: {e}")
        return False
    finally:
        # API ishlashiga xalaqit bermasligi uchun sessiyani yopamiz
        await bot.session.close()