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
    # 1. Kontakt haqqoniyligini tekshirish
    if message.contact.user_id != message.from_user.id:
        return await message.answer("❌ Faqat o'z kontaktingizni yuboring.")

    phone = normalize_phone(message.contact.phone_number)
    state_data = await state.get_data()
    external_uid = state_data.get("external_user_id")

    async with AsyncSessionLocal() as db:
        # 2. Foydalanuvchini aniqlash
        user = None
        if external_uid and external_uid.isdigit():
            # Agar deep-linkdan ID kelgan bo'lsa (Google user yoki profilni tahrirlash)
            stmt = select(User).where(User.id == int(external_uid))
            user = (await db.execute(stmt)).scalar_one_or_none()
        
        if not user:
            # Agar ID kelmagan bo'lsa, raqam orqali qidiramiz
            stmt = select(UserContact).where(UserContact.value == phone).options(selectinload(UserContact.user))
            contact_record = (await db.execute(stmt)).scalar_one_or_none()
            if contact_record:
                user = contact_record.user

        # 3. Agar foydalanuvchi hali ham topilmasa
        if not user:
            return await message.answer("❌ Foydalanuvchi topilmadi. Avval saytdan ro'yxatdan o'ting.")

        # 4. Raqamni foydalanuvchiga bog'lash (Contact qo'shish yoki yangilash)
        # Avval bu raqam ushbu foydalanuvchida bor-yo'qligini tekshiramiz
        stmt_check = select(UserContact).where(
            and_(UserContact.user_id == user.id, UserContact.value == phone)
        )
        existing_contact = (await db.execute(stmt_check)).scalar_one_or_none()

        if not existing_contact:
            # Agar raqam foydalanuvchiga biriktirilmagan bo'lsa, yangi kontakt qo'shamiz
            new_contact = UserContact(
                user_id=user.id,
                contact_type='phone',
                value=phone,
                is_verified=False  # Hali OTP kiritilmagan
            )
            db.add(new_contact)
            await db.flush() # ID ni olish uchun lekin commit qilmasdan
        
        # 5. OTP yaratish va saqlash
        otp = generate_otp()
        
        # Maqsadni aniqlash
        purpose = VerificationPurpose.ADD_CONTACT if external_uid else VerificationPurpose.LOGIN
        
        db.add(VerificationCode(
            user_id=user.id,
            target=phone,
            code=otp,
            purpose=purpose,
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        ))
        
        await db.commit()

        # 6. Foydalanuvchiga javob yuborish
        response_text = (
            f"✅ <b>Raqam qabul qilindi!</b>\n\n"
            f"Sizning tasdiqlash kodingiz: <code>{otp}</code>\n\n"
            f"Ushbu kodni saytga kiriting. Kod 5 daqiqa davomida amal qiladi."
        )
        
        await message.answer(response_text, parse_mode="HTML", reply_markup=get_main_keyboard())

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