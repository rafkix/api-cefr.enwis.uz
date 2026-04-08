from datetime import datetime, timedelta, timezone

from aiogram import Router, F, types
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.inline import get_sub_keyboard
from app.bot.keyboards.reply import get_contact_keyboard, get_main_keyboard
from app.bot.states.states import AuthFlow
from app.bot.utils.helpers import check_subscription, generate_otp, hash_code, normalize_phone
from app.core.database import AsyncSessionLocal
from app.modules.auth.models import VerificationCode

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    args = command.args

    if not await check_subscription(message.bot, message.from_user.id):
        return await message.answer(
            "👋 Xush kelibsiz. Botdan foydalanish uchun avval kanalga a'zo bo'ling.",
            reply_markup=get_sub_keyboard(args),
        )

    if args:
        # 1) Saytdagi userni telegramga bog'lash: /start login_12345
        if args.startswith("login_"):
            raw_user_id = args.replace("login_", "").strip()
            if raw_user_id.isdigit():
                await state.update_data(external_user_id=int(raw_user_id))
                await state.set_state(AuthFlow.waiting_contact_login)
                return await message.answer(
                    "📱 Saytdagi profilingizni Telegram bilan bog'lash uchun kontaktingizni yuboring.",
                    reply_markup=get_contact_keyboard(),
                )

        # 2) Telefon tasdiqlash flow
        if args == "verify_phone":
            await state.set_state(AuthFlow.waiting_contact_verify)
            return await message.answer(
                "📱 Telefon raqamingizni tasdiqlash uchun kontaktingizni yuboring.",
                reply_markup=get_contact_keyboard(),
            )

        # 3) SMS code / OTP flow
        # sms_998901234567 yoki 998901234567
        potential_phone = args.replace("sms_", "").split("_")[0].strip()

        if potential_phone.isdigit() and len(potential_phone) >= 9:
            phone = normalize_phone(potential_phone)
            otp_code = generate_otp()

            async with AsyncSessionLocal() as db:
                db.add(
                    VerificationCode(
                        target=phone,
                        code_hash=hash_code(otp_code),
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                        is_used=False,
                    )
                )
                await db.commit()

            return await message.answer(
                f"🔢 Tasdiqlash kodingiz: <code>{otp_code}</code>\n\n"
                f"Ushbu kodni <b>{phone}</b> raqami uchun saytdagi maydonga kiriting.\n"
                f"⌛ Amal qilish muddati: 5 daqiqa.",
                parse_mode="HTML",
            )

        return await message.answer(
            "❌ Noto'g'ri start argument yuborildi.",
            reply_markup=get_main_keyboard(),
        )

    await message.answer(
        f"Xush kelibsiz, {message.from_user.first_name}!\n"
        "Profilingizni boshqarish uchun quyidagi menyudan foydalaning.",
        reply_markup=get_main_keyboard(),
    )


@router.callback_query(F.data.startswith("check_sub"))
async def process_check_sub(callback: types.CallbackQuery, state: FSMContext):
    is_sub = await check_subscription(callback.bot, callback.from_user.id)

    if not is_sub:
        return await callback.answer("❌ Siz hali kanalga a'zo emassiz.", show_alert=True)

    await callback.answer("✅ Rahmat! Obuna tasdiqlandi.")

    data_parts = callback.data.split(":", maxsplit=1)
    args = data_parts[1] if len(data_parts) > 1 and data_parts[1] != "None" else None

    try:
        await callback.message.delete()
    except Exception:
        pass

    await cmd_start(
        callback.message,
        CommandObject(prefix="/", command="start", mention=None, args=args),
        state,
    )