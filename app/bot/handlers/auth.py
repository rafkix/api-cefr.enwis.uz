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
    
@router.message(AuthFlow.waiting_contact_verify, F.contact)
async def process_verify_contact(message: types.Message, state: FSMContext):
    # 1. Kontakt egasini tekshirish
    if message.contact.user_id != message.from_user.id:
        return await message.answer("❌ Faqat o'z kontaktingizni yuboring.")

    contact_phone = normalize_phone(message.contact.phone_number)
    tg_id = str(message.from_user.id)

    async with AsyncSessionLocal() as db:
        try:
            # 2. Telefon raqami bazada borligini tekshirish
            stmt_phone = select(UserContact).where(
                and_(
                    UserContact.contact_type == 'phone',
                    UserContact.value == contact_phone
                )
            )
            phone_res = await db.execute(stmt_phone)
            db_phone_contact = phone_res.scalar_one_or_none()

            if not db_phone_contact:
                return await message.answer(
                    "❌ Bu telefon raqami tizimda topilmadi.\n"
                    "Iltimos, avval saytda ro'yxatdan o'ting."
                )

            # 3. Telefonni tasdiqlangan (verified) holatga keltirish
            db_phone_contact.is_verified = True
            u_id = db_phone_contact.user_id # Foydalanuvchi ID sini olamiz

            # 4. Telegram ID kontaktini tekshirish/qo'shish
            stmt_tg = select(UserContact).where(
                and_(
                    UserContact.user_id == u_id,
                    UserContact.contact_type == 'telegram'
                )
            )
            tg_res = await db.execute(stmt_tg)
            db_tg_contact = tg_res.scalar_one_or_none()

            if db_tg_contact:
                # Agar telegram kontakti bo'lsa, ID ni yangilaymiz
                db_tg_contact.value = tg_id
                db_tg_contact.is_verified = True
            else:
                # Agar telegram kontakti bo'lmasa, yangi qo'shamiz
                db.add(UserContact(
                    user_id=u_id,
                    contact_type='telegram',
                    value=tg_id,
                    is_verified=True
                ))

            # 5. Saqlash
            await db.commit()
            
            await message.answer(
                "✅ <b>Tabriklaymiz! Profilingiz tasdiqlandi.</b>\n\n"
                "Endi saytda barcha imkoniyatlardan foydalanishingiz mumkin.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            await state.clear()

        except Exception as e:
            await db.rollback()
            print(f"Verification Error: {e}")
            await message.answer("❌ Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.")
@router.message(F.text == "🔑 Parolni o'zgartirish")
async def start_change_pw(message: types.Message, state: FSMContext):
    if not await check_subscription(message.bot, message.from_user.id): return
    await state.set_state(AuthFlow.waiting_contact_password)
    await message.answer("Xavfsizlik uchun kontaktingizni yuboring:", reply_markup=get_contact_keyboard())

@router.message(AuthFlow.waiting_contact_forgot, F.contact)
async def process_forgot_password_contact(message: types.Message, state: FSMContext):
    contact_phone = normalize_phone(message.contact.phone_number)
    
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(UserContact).where(UserContact.value == contact_phone))
        contact = res.scalar_one_or_none()
        
        if not contact:
            return await message.answer("❌ Bu raqamli profil topilmadi.")

        await state.update_data(reset_user_id=contact.user_id)
        await state.set_state(AuthFlow.waiting_new_password)
        await message.answer("Keyingi qadam: Endi yangi parolni yozib yuboring:")

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