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
    if message.contact.user_id != message.from_user.id:
        return await message.answer("❌ Faqat o'z kontaktingizni yuboring.")

    contact_phone = normalize_phone(message.contact.phone_number)
    tg_id = str(message.from_user.id)
    
    state_data = await state.get_data()
    user_id_from_site = state_data.get("external_user_id")

    async with AsyncSessionLocal() as db:
        if user_id_from_site:
            u_id = int(user_id_from_site)
            
            # 1. Asosiy User jadvalidagi telegram_id ni yangilash
            await db.execute(
                update(User).where(User.id == u_id).values(telegram_id=tg_id)
            )

            # 2. KONTAKTLARNI SAQLASH (Telefon va Telegram ID)
            # Bizga telefon va telegram kontaktlarini tekshirish kerak
            stmt = select(UserContact).where(
                and_(
                    UserContact.user_id == u_id, 
                    UserContact.contact_type.in_(['phone', 'telegram'])
                )
            )
            existing_contacts = (await db.execute(stmt)).scalars().all()
            
            contact_map = {c.contact_type: c for c in existing_contacts}

            # --- Telefon raqami uchun ---
            if 'phone' in contact_map:
                contact_map['phone'].value = contact_phone
                contact_map['phone'].is_verified = True
            else:
                db.add(UserContact(
                    user_id=u_id, contact_type='phone', 
                    value=contact_phone, is_verified=True
                ))

            # --- Telegram ID uchun (Yangi qo'shildi) ---
            if 'telegram' in contact_map:
                contact_map['telegram'].value = tg_id
                contact_map['telegram'].is_verified = True
            else:
                db.add(UserContact(
                    user_id=u_id, contact_type='telegram', 
                    value=tg_id, is_verified=True
                ))

            await db.commit()
            
            await message.answer(
                f"✅ <b>Muvaffaqiyatli bog'landi!</b>\n\n"
                f"📱 Telefon: <code>{contact_phone}</code>\n"
                f"🔹 Telegram ID: <code>{tg_id}</code>\n\n"
                f"Barcha ma'lumotlar tasdiqlandi. Saytga qaytishingiz mumkin.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer("❌ Xatolik: Sayt orqali bog'lanish seansi topilmadi.")

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