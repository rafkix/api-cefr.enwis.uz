import asyncio
import logging
import aiohttp
import re

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, CommandObject
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from app.bot.handlers import router as registration_router

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


API_BASE_URL = "http://127.0.0.1:8000"
BOT_TOKEN = "8235003520:AAE7bWueai7Gx3ZzAs0H_cR-9AFQhrWwaWA"


bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

router = Router()

@router.message(CommandStart())
async def start_handler(
    message: Message,
    command: CommandObject,
    state: FSMContext
):
    args = command.args

    # =====================
    # 1️⃣ ARGUMENT TEKSHIRISH
    # =====================
    if not args:
        await message.answer(
            "❌ <b>Xatolik</b>\n\n"
            "Botga faqat sayt orqali kirish mumkin.\n"
            "Raqamingiz tasdiqlanmagan.",
            parse_mode="HTML"
        )
        return

    # =====================
    # 2️⃣ TELEFON TOZALASH
    # =====================
    raw_phone = (
        args.replace("%20", "")
            .replace(" ", "")
            .replace("+", "")
            .strip()
    )
    clean_phone = re.sub(r"\D", "", raw_phone)

    if len(clean_phone) < 9:
        await message.answer("❌ Noto‘g‘ri telefon raqami.")
        return

    # =====================
    # 3️⃣ BACKEND REQUEST
    # =====================
    url = f"{API_BASE_URL}/v1/api/auth/bot/start"
    payload = {
        "phone": clean_phone,
        "telegram_id": int(message.from_user.id),
        "full_name": message.from_user.full_name or "Unknown",
    }

    logging.info(f"BOT START PAYLOAD => {payload}")

    try:
        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:

                # JSON xavfsiz o‘qish
                try:
                    data = await response.json()
                except Exception:
                    await message.answer("❌ Backend noto‘g‘ri javob qaytardi.")
                    return

                if response.status != 200:
                    detail = data.get("detail", "Noma'lum xatolik")
                    await message.answer(f"❌ Xatolik: {detail}")
                    return

                logging.info(f"BOT START RESPONSE => {data}")

                # =====================
                # 4️⃣ RESPONSE ANALYZE
                # =====================
                is_new_user = data.get("is_new_user", False)

                # -------- YANGI USER --------
                if is_new_user is True:
                    kb = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="📝 Ro'yxatdan o'tish",
                                    callback_data="start_register_flow"
                                )
                            ]
                        ]
                    )

                    await state.update_data(phone=clean_phone)

                    await message.answer(
                        f"👋 <b>Salom!</b>\n\n"
                        f"Sizning raqamingiz (<code>{clean_phone}</code>) bazada topilmadi.\n"
                        "Xizmatlardan foydalanish uchun ro'yxatdan o'ting:",
                        reply_markup=kb,
                        parse_mode="HTML"
                    )
                    return

                # -------- MAVJUD USER --------
                code = data.get("code")

                if not code:
                    logging.error(f"CODE NOT FOUND => {data}")
                    await message.answer(
                        "❌ Tasdiqlash kodi topilmadi.\n"
                        "Iltimos saytga qaytib qayta urinib ko‘ring."
                    )
                    return

                reg_kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🌐 Saytga qaytish",
                                url="https://enwis.uz"
                            )
                        ]
                    ]
                )

                await message.answer(
                    "🔐 <b>Tasdiqlash kodi</b>\n\n"
                    f"<code>{code}</code>\n\n"
                    "⏳ Kod 5 daqiqa amal qiladi.\n"
                    "🌐 Uni saytga qaytib kiriting.",
                    reply_markup=reg_kb,
                    parse_mode="HTML"
                )

    # =====================
    # 5️⃣ NETWORK ERRORS
    # =====================
    except aiohttp.ClientConnectorError:
        await message.answer(
            "❌ Backend serverga ulanib bo‘lmadi.\n"
            "Server ishlayotganini tekshiring."
        )

    except asyncio.TimeoutError:
        await message.answer("❌ Server javobi juda sekin.")

    except Exception:
        logging.exception("BOT START HANDLER ERROR")
        await message.answer(
            "❌ Kutilmagan xatolik yuz berdi.\n"
            "Iltimos, keyinroq urinib ko‘ring."
        )


async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Routerlarni qo'shish (Tartib muhim: avval registratsiya, keyin start)
    dp.include_router(registration_router)
    dp.include_router(router)
    
    print("🤖 Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    async def run():
        try:
            await main()
        except KeyboardInterrupt:
            print("Bot to'xtatildi")

    asyncio.run(run())