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

    if not await check_subscription(message.bot, message.from_user.id):
        return await message.answer("👋 Xush kelibsiz! Botdan foydalanish uchun kanalga a'zo bo'ling.", 
                                    reply_markup=get_sub_keyboard(args))

    if args == "forgot_password":
        await state.set_state(AuthFlow.waiting_contact_forgot)
        return await message.answer("🔐 Parolni tiklash uchun kontaktingizni yuboring:", reply_markup=get_contact_keyboard())

    if args and (args.isdigit() or args.startswith("998")):
        phone = normalize_phone(args)
        await state.update_data(login_phone=phone)
        await state.set_state(AuthFlow.waiting_contact_login)
        return await message.answer(f"🔐 {phone} raqamini tasdiqlash uchun kontaktingizni yuboring:", reply_markup=get_contact_keyboard())

    await message.answer(f"Xush kelibsiz, {message.from_user.first_name}!", reply_markup=get_main_keyboard())

@router.callback_query(F.data.startswith("check_sub"))
async def process_check_sub(callback: types.CallbackQuery, state: FSMContext):
    is_sub = await check_subscription(callback.bot, callback.from_user.id)
    if is_sub:
        await callback.answer("✅ Rahmat! Obuna tasdiqlandi.")
        args = callback.data.split(":")[1] if ":" in callback.data else None
        await callback.message.delete()
        await cmd_start(callback.message, CommandObject(args=args, command="start"), state)
    else:
        await callback.answer("❌ Siz hali kanalga a'zo emassiz!", show_alert=True)