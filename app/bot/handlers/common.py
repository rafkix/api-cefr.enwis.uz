from aiogram import Router, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from app.bot.utils.helpers import check_subscription, normalize_phone
from app.bot.keyboards.reply import get_main_keyboard, get_contact_keyboard
from app.bot.keyboards.inline import get_sub_keyboard
from app.bot.states.states import AuthFlow

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    args = command.args

    # 1. Obunani tekshirish (majburiy kanal)
    if not await check_subscription(message.bot, message.from_user.id):
        return await message.answer(
            "👋 Xush kelibsiz! Botdan foydalanish uchun kanalga a'zo bo'ling.", 
            reply_markup=get_sub_keyboard(args)
        )

    # 2. Argumentlarni tahlil qilish
    if args:
        # A. SMS kod berish holati (sms_998901234567)
        if args.startswith("sms_"):
            phone = normalize_phone(args.replace("sms_", ""))
            otp_code = generate_otp()
            
            async with AsyncSessionLocal() as db:
                db.add(VerificationCode(
                    value=phone,
                    code=otp_code,
                    purpose=VerificationPurpose.PHONE_VERIFICATION,
                    expires_at=datetime.utcnow() + timedelta(minutes=5)
                ))
                await db.commit()
            
            return await message.answer(
                f"🔢 Tasdiqlash kodingiz: <code>{otp_code}</code>\n\n"
                f"Uni saytdagi maydonga kiriting. Amal qilish muddati: 5 daqiqa.",
                parse_mode="HTML"
            )

        # B. Parolni tiklash holati
        if args == "forgot_password":
            await state.set_state(AuthFlow.waiting_contact_forgot)
            return await message.answer(
                "🔐 Parolni tiklash uchun kontaktingizni yuboring:", 
                reply_markup=get_contact_keyboard()
            )

        # C. Raqam va UserID ni bog'lash holati (998901234567_102)
        # "_" belgisi orqali ajratamiz
        parts = args.split("_")
        potential_phone = parts[0]
        
        if potential_phone.isdigit() and len(potential_phone) >= 9:
            phone = normalize_phone(potential_phone)
            # Agar "_" dan keyin ID kelsa, uni saqlaymiz (masalan: 102)
            extra_user_id = parts[1] if len(parts) > 1 else None
            
            await state.update_data(
                login_phone=phone,
                external_user_id=extra_user_id
            )
            
            await state.set_state(AuthFlow.waiting_contact_login)
            return await message.answer(
                f"🤝 {phone} raqamini profilingizga bog'lash va tasdiqlash uchun "
                f"pastdagi tugma orqali kontaktingizni yuboring:", 
                reply_markup=get_contact_keyboard()
            )

        # D. Oddiy tasdiqlash (verify_phone)
        if args == "verify_phone":
            await state.set_state(AuthFlow.waiting_contact_login)
            return await message.answer(
                "📱 Telefon raqamingizni tasdiqlash uchun kontaktingizni yuboring:", 
                reply_markup=get_contact_keyboard()
            )

    # 3. Argument yo'q bo'lsa yoki shunchaki kirgan bo'lsa
    await message.answer(
        f"Xush kelibsiz, {message.from_user.first_name}!\n"
        "Profilingizni boshqarish uchun saytdan foydalaning.", 
        reply_markup=get_main_keyboard()
    )

@router.callback_query(F.data.startswith("check_sub"))
async def process_check_sub(callback: types.CallbackQuery, state: FSMContext):
    is_sub = await check_subscription(callback.bot, callback.from_user.id)
    if is_sub:
        await callback.answer("✅ Rahmat! Obuna tasdiqlandi.")
        # Callback datadan argumentni olish: check_sub:argument_shuyerda
        data_parts = callback.data.split(":")
        args = data_parts[1] if len(data_parts) > 1 and data_parts[1] != "None" else None
        
        await callback.message.delete()
        # Argumentni CommandObject ko'rinishida qayta start funksiyasiga uzatish
        await cmd_start(callback.message, CommandObject(args=args, command="start"), state)
    else:
        await callback.answer("❌ Siz hali kanalga a'zo emassiz!", show_alert=True)