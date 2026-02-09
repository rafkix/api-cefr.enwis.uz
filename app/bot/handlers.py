import re
import aiohttp
import logging
from aiogram import Router, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    CallbackQuery,
)
from aiogram.fsm.context import FSMContext
from app.bot.states import UserRegisterState

router = Router()
API_BASE_URL = "http://127.0.0.1:8000"

EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[a-zA-Z0-9]+$"


# =========================
# 1️⃣ START REGISTER
# =========================
@router.callback_query(F.data == "start_register_flow")
async def start_register(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except:
        pass

    await state.clear()
    await state.set_state(UserRegisterState.waiting_for_full_name)

    await callback.message.answer(
        "📝 <b>Ro'yxatdan o'tish boshlandi</b>\n\n"
        "Iltimos, <b>to‘liq ismingizni</b> kiriting:",
        parse_mode="HTML",
    )


# =========================
# 2️⃣ FULL NAME
# =========================
@router.message(UserRegisterState.waiting_for_full_name)
async def full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(UserRegisterState.waiting_for_username)

    await message.answer(
        "👤 Endi <b>username</b> tanlang\n"
        "(faqat lotin harflari va sonlar):",
        parse_mode="HTML",
    )


# =========================
# 3️⃣ USERNAME
# =========================
@router.message(UserRegisterState.waiting_for_username)
async def username(message: Message, state: FSMContext):
    if not re.fullmatch(r"[a-zA-Z0-9_]{4,30}", message.text):
        return await message.answer("❌ Username noto‘g‘ri. Qayta kiriting:")

    # 🔑 UNIQUE QILIB QO‘YAMIZ
    unique_username = f"{message.text.lower()}_{message.from_user.id}"

    await state.update_data(username=unique_username)
    await state.set_state(UserRegisterState.waiting_for_email)

    await message.answer("📧 <b>Email</b> kiriting:", parse_mode="HTML")


# =========================
# 4️⃣ EMAIL
# =========================
@router.message(UserRegisterState.waiting_for_email)
async def email(message: Message, state: FSMContext):
    if not re.match(EMAIL_REGEX, message.text):
        return await message.answer("❌ Email formati noto‘g‘ri. Masalan: test@gmail.com")

    await state.update_data(email=message.text.lower())
    await state.set_state(UserRegisterState.waiting_for_password)

    await message.answer(
        "🔒 <b>Parol</b> yarating (kamida 8 ta belgi):",
        parse_mode="HTML",
    )


# =========================
# 5️⃣ PASSWORD
# =========================
@router.message(UserRegisterState.waiting_for_password)
async def password(message: Message, state: FSMContext):
    if len(message.text) < 8:
        return await message.answer("❌ Parol juda qisqa. Kamida 8 ta belgi bo‘lsin.")

    await state.update_data(password=message.text)
    await state.set_state(UserRegisterState.waiting_for_age)

    await message.answer("🔢 <b>Yoshingizni</b> kiriting:", parse_mode="HTML")


# =========================
# 6️⃣ AGE
# =========================
@router.message(UserRegisterState.waiting_for_age)
async def age(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) < 10:
        return await message.answer("❌ Yoshingizni to‘g‘ri kiriting:")

    await state.update_data(age=int(message.text))
    await state.set_state(UserRegisterState.waiting_for_level)

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="beginner"), KeyboardButton(text="elementary")],
            [KeyboardButton(text="intermediate"), KeyboardButton(text="advanced")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(
        "📊 Ingliz tili darajangizni tanlang:",
        reply_markup=kb,
    )


# =========================
# 7️⃣ LEVEL
# =========================
@router.message(UserRegisterState.waiting_for_level)
async def level(message: Message, state: FSMContext):
    await state.update_data(level=message.text)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await state.set_state(UserRegisterState.waiting_for_phone)
    await message.answer(
        "📱 Telefon raqamingizni yuboring:",
        reply_markup=kb,
    )


# =========================
# 8️⃣ FINAL REGISTER
# =========================
@router.message(UserRegisterState.waiting_for_phone)
async def finish_register(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    clean_phone = re.sub(r"\D", "", phone or "")

    if len(clean_phone) < 9:
        return await message.answer("❌ Telefon raqami noto‘g‘ri.")

    data = await state.get_data()

    payload = {
        "full_name": data["full_name"],
        "username": data["username"],
        "email": data["email"],
        "password": data["password"],
        "phone": clean_phone,
        "age": data["age"],
        "level": data["level"],
        "role": "student",
        "telegram_id": message.from_user.id,
    }

    logging.warning(f"REGISTER PAYLOAD => {payload}")

    msg = await message.answer("⏳ Hisob yaratilmoqda...", reply_markup=ReplyKeyboardRemove())

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            reg_url = f"{API_BASE_URL}/v1/api/auth/register/telegram"
            async with session.post(reg_url, json=payload) as r:
                if r.status not in (200, 201):
                    err = await r.json()
                    await msg.delete()
                    return await message.answer(f"❌ Xatolik: {err.get('detail')}")

            start_url = f"{API_BASE_URL}/v1/api/auth/bot/start"
            async with session.post(
                start_url,
                json={
                    "phone": clean_phone,
                    "telegram_id": message.from_user.id,
                    "full_name": data["full_name"],
                },
            ) as s:
                code = (await s.json()).get("code")

        await msg.delete()
        await state.clear()

        await message.answer(
            f"✅ <b>Muvaffaqiyatli ro‘yxatdan o‘tdingiz!</b>\n\n"
            f"🔐 <b>Kirish kodingiz:</b>\n"
            f"<code>{code}</code>\n\n"
            f"🌐 Saytga qaytib ushbu kodni kiriting.",
            parse_mode="HTML",
        )

    except Exception:
        logging.exception("REGISTER ERROR")
        await msg.delete()
        await message.answer("❌ Tizimda xatolik. Keyinroq urinib ko‘ring.")
