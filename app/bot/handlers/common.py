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
        # A & C. Telefon raqami kelganda (sms_998... yoki shunchaki 998...)
        # Raqamni tozalab olamiz
        potential_phone = args.replace("sms_", "").split("_")[0]
        
        if potential_phone.isdigit() and len(potential_phone) >= 9:
            phone = normalize_phone(potential_phone)
            otp_code = generate_otp()
            
            async with AsyncSessionLocal() as db:
                # Eskirgan yoki avvalgi kodlarni o'chirish (ixtiyoriy, tartib uchun)
                db.add(VerificationCode(
                    value=phone,
                    code=otp_code,
                    purpose=VerificationPurpose.PHONE_VERIFICATION,
                    expires_at=datetime.utcnow() + timedelta(minutes=5)
                ))
                await db.commit()
            
            return await message.answer(
                f"🔢 Tasdiqlash kodingiz: <code>{otp_code}</code>\n\n"
                f"Ushbu kodni <b>{phone}</b> raqami uchun saytdagi maydonga kiriting.\n"
                f"⌛ Amal qilish muddati: 5 daqiqa.",
                parse_mode="HTML"
            )

        # B. Parolni tiklash holati
        if args == "forgot_password":
            await state.set_state(AuthFlow.waiting_contact_forgot)
            return await message.answer(
                "🔐 Parolni tiklash uchun kontaktingizni yuboring:", 
                reply_markup=get_contact_keyboard()
            )

        # D. Oddiy tasdiqlash so'rovi (agar raqamsiz kelsa)
        if args == "verify_phone":
            await state.set_state(AuthFlow.waiting_contact_login)
            return await message.answer(
                "📱 Telefon raqamingizni tasdiqlash uchun pastdagi tugma orqali kontaktingizni yuboring:", 
                reply_markup=get_contact_keyboard()
            )

    # 3. Argument yo'q bo'lsa yoki noto'g'ri argument bo'lsa
    await message.answer(
        f"Xush kelibsiz, {message.from_user.first_name}!\n"
        "Profilingizni tasdiqlash yoki boshqarish uchun saytimizdan foydalaning.", 
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