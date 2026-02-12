from aiogram import Router, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from utils.helpers import check_subscription, normalize_phone
from keyboards.reply import get_main_keyboard, get_contact_keyboard
from keyboards.inline import get_sub_keyboard
from states.states import AuthFlow

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    args = command.args

    # 1. Obunani tekshirish
    if not await check_subscription(message.bot, message.from_user.id):
        return await message.answer(
            "👋 Xush kelibsiz! Botdan foydalanish uchun kanalga a'zo bo'ling.", 
            reply_markup=get_sub_keyboard(args)
        )

    # 2. Argumentlarni tahlil qilish
    if args:
        # Parolni tiklash holati
        if args == "forgot_password":
            await state.set_state(AuthFlow.waiting_contact_forgot)
            return await message.answer("🔐 Parolni tiklash uchun kontaktingizni yuboring:", reply_markup=get_contact_keyboard())

        # Telefon raqami va qo'shimcha ma'lumotlarni tahlil qilish (masalan: "998901234567_102" yoki "998901234567")
        # Biz "_" belgisidan bo'lib olamiz
        parts = args.split("_")
        potential_phone = parts[0]
        
        if potential_phone.isdigit() or potential_phone.startswith("998"):
            phone = normalize_phone(potential_phone)
            
            # Agar "_" dan keyin nimadir bo'lsa (masalan user_id), uni ham saqlab qo'yamiz
            extra_info = parts[1] if len(parts) > 1 else None
            
            await state.update_data(
                login_phone=phone,
                external_user_id=extra_info # Kerak bo'lsa keyin ishlatish uchun
            )
            
            await state.set_state(AuthFlow.waiting_contact_login)
            return await message.answer(
                f"🔐 {phone} raqamini tasdiqlash uchun kontaktingizni yuboring:", 
                reply_markup=get_contact_keyboard()
            )
            
        # Agar argument "verify_phone" bo'lsa (Frontend'dagi oddiy holat uchun)
        if args == "verify_phone":
            await state.set_state(AuthFlow.waiting_contact_login)
            return await message.answer("📱 Telefon raqamingizni tasdiqlash uchun kontaktingizni yuboring:", reply_markup=get_contact_keyboard())

    # Argument yo'q bo'lsa yoki tushunarsiz bo'lsa
    await message.answer(f"Xush kelibsiz, {message.from_user.first_name}!", reply_markup=get_main_keyboard())

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