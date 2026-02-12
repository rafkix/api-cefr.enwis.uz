from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.modules.auth.models import User, UserContact, UserIdentity, VerificationCode, VerificationPurpose, AuthProvider
from app.bot.utils.helpers import normalize_phone, generate_otp, check_subscription
from app.bot.states.states import AuthFlow
from app.bot.keyboards.reply import get_main_keyboard, get_contact_keyboard

router = Router()

@router.message(AuthFlow.waiting_contact_login, F.contact)
async def process_login_contact(message: types.Message, state: FSMContext):
    # 1. Faqat foydalanuvchining o'z kontaktini qabul qilamiz (xavfsizlik uchun)
    if message.contact.user_id != message.from_user.id:
        return await message.answer("❌ Faqat o'z kontaktingizni yuboring.")

    phone = normalize_phone(message.contact.phone_number)
    tg_id = str(message.from_user.id) # Telegram User ID
    
    # State ichidan Frontend yuborgan user_id ni olamiz
    state_data = await state.get_data()
    user_id_from_site = state_data.get("external_user_id")

    if not user_id_from_site:
        return await message.answer("❌ Tizimda xatolik: User ID topilmadi. Saytdan qaytadan urinib ko'ring.")

    async with AsyncSessionLocal() as db:
        # 2. Asosiy User jadvalini yangilash (Telegram ID ni saqlash)
        # UserIdentity yoki User modeliga telegram_id ni yozamiz
        await db.execute(
            update(User)
            .where(User.id == int(user_id_from_site))
            .values(telegram_id=tg_id)
        )

        # 3. UserContact jadvaliga telefon raqamini qo'shish yoki yangilash
        # Avval bu userda ushbu raqam borligini tekshiramiz
        stmt_check = select(UserContact).where(
            and_(
                UserContact.user_id == int(user_id_from_site), 
                UserContact.contact_type == 'phone'
            )
        )
        existing_contact = (await db.execute(stmt_check)).scalar_one_or_none()

        if existing_contact:
            # Agar kontakt bo'lsa, raqamni va statusni yangilaymiz
            existing_contact.value = phone
            existing_contact.is_verified = True
        else:
            # Agar kontakt bo'lmasa, yangisini yaratamiz
            new_contact = UserContact(
                user_id=int(user_id_from_site),
                contact_type='phone',
                value=phone,
                is_verified=True # Telegramdan kelgani uchun darhol tasdiqlangan
            )
            db.add(new_contact)

        # 4. Saqlash
        await db.commit()

        # 5. Foydalanuvchiga muvaffaqiyatli xabar yuborish
        await message.answer(
            f"✅ <b>Muvaffaqiyatli bog'landi!</b>\n\n"
            f"📱 Raqam: <code>{phone}</code>\n"
            f"🆔 Telegram ID: <code>{tg_id}</code>\n\n"
            f"Profilingiz tasdiqlandi. Endi saytga qaytib sahifani yangilashingiz mumkin.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )

    await state.clear()

@router.message(F.text == "🔑 Parolni o'zgartirish")
async def start_change_pw(message: types.Message, state: FSMContext):
    if not await check_subscription(message.bot, message.from_user.id): return
    await state.set_state(AuthFlow.waiting_contact_password)
    await message.answer("Xavfsizlik uchun kontaktingizni yuboring:", reply_markup=get_contact_keyboard())

@router.message(AuthFlow.waiting_new_password)
async def save_new_pw(message: types.Message, state: FSMContext):
    if not message.text or len(message.text) < 8:
        return await message.answer("⚠️ Parol kamida 8 ta belgi bo'lsin!")
    
    data = await state.get_data()
    uid = data.get("target_user_id")
    async with AsyncSessionLocal() as db:
        await db.execute(update(UserIdentity).where(and_(UserIdentity.user_id == uid, UserIdentity.provider == AuthProvider.LOCAL))
                         .values(password_hash=hash_password(message.text[:70])))
        await db.commit()
    await message.answer("✅ Parol yangilandi!", reply_markup=get_main_keyboard())
    await state.clear()