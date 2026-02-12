from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.modules.auth.models import User, UserContact, UserIdentity, VerificationCode, VerificationPurpose, AuthProvider
from utils.helpers import normalize_phone, generate_otp, check_subscription
from states.states import AuthFlow
from keyboards.reply import get_main_keyboard, get_contact_keyboard

router = Router()

@router.message(AuthFlow.waiting_contact_login, F.contact)
async def process_login_contact(message: types.Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        return await message.answer("❌ Faqat o'z kontaktingizni yuboring.")

    phone = normalize_phone(message.contact.phone_number)
    async with AsyncSessionLocal() as db:
        stmt = select(UserContact).where(UserContact.value == phone)
        contact = (await db.execute(stmt)).scalar_one_or_none()
        if not contact: return await message.answer("❌ Bu raqam ro'yxatda yo'q.")

        otp = generate_otp()
        db.add(VerificationCode(user_id=contact.user_id, target=phone, code=otp, purpose=VerificationPurpose.LOGIN, 
                                expires_at=datetime.utcnow() + timedelta(minutes=5)))
        await db.commit()
        await message.answer(f"✅ Kirish kodingiz: <code>{otp}</code>")
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