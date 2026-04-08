from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.bot.keyboards.inline import get_user_manage_kb
from app.bot.keyboards.reply import get_admin_keyboard
from app.bot.utils.helpers import is_admin
from app.core.database import AsyncSessionLocal
from app.modules.auth.models import AuthProvider, User, UserContact, UserIdentity

router = Router()


@router.message(F.text.in_({"/admin", "🛠 Admin panel"}))
async def admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("🛠 Admin panel", reply_markup=get_admin_keyboard())


@router.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if not await is_admin(message.from_user.id):
        return

    async with AsyncSessionLocal() as db:
        total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0

        telegram_users = (
            await db.execute(
                select(func.count(UserIdentity.id)).where(
                    UserIdentity.provider == AuthProvider.TELEGRAM
                )
            )
        ).scalar() or 0

        verified_phones = (
            await db.execute(
                select(func.count(UserContact.id)).where(
                    (UserContact.contact_type == "PHONE") & (UserContact.is_verified.is_(True))
                )
            )
        ).scalar() or 0

    await message.answer(
        f"📈 Jami foydalanuvchilar: {total_users}\n"
        f"🔗 Telegram ulanganlar: {telegram_users}\n"
        f"📱 Tasdiqlangan telefonlar: {verified_phones}"
    )


@router.message(F.text == "👥 Foydalanuvchilarni boshqarish")
async def manage_users_list(message: types.Message):
    if not await is_admin(message.from_user.id):
        return

    async with AsyncSessionLocal() as db:
        users = (
            await db.execute(
                select(User)
                .options(selectinload(User.profile))
                .order_by(User.created_at.desc())
                .limit(10)
            )
        ).scalars().all()

    if not users:
        return await message.answer("Foydalanuvchilar topilmadi.")

    builder = InlineKeyboardBuilder()

    for user in users:
        full_name = user.profile.full_name if user.profile and user.profile.full_name else str(user.id)
        builder.row(
            types.InlineKeyboardButton(
                text=f"👤 {full_name}",
                callback_data=f"user_info:{user.id}",
            )
        )

    await message.answer("So'nggi foydalanuvchilar:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("user_info:"))
async def show_user_detail(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return await callback.answer("Ruxsat yo'q.", show_alert=True)

    user_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(
                select(User)
                .options(
                    selectinload(User.profile),
                    selectinload(User.contacts),
                    selectinload(User.identities),
                )
                .where(User.id == user_id)
            )
        ).scalar_one_or_none()

    if not user:
        return await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)

    full_name = user.profile.full_name if user.profile and user.profile.full_name else "Noma'lum"
    status = "🔴 Bloklangan" if not user.is_active else "🟢 Faol"

    phones = [c.value for c in user.contacts if str(c.contact_type).endswith("PHONE")]
    telegrams = [c.value for c in user.contacts if str(c.contact_type).endswith("TELEGRAM")]

    info_text = (
        f"👤 <b>Foydalanuvchi ma'lumotlari</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📝 Ism: <b>{full_name}</b>\n"
        f"🎭 Role: <b>{user.global_role.value}</b>\n"
        f"📊 Holati: <b>{status}</b>\n"
        f"📱 Telefon(lar): <code>{', '.join(phones) if phones else 'yo‘q'}</code>\n"
        f"📨 Telegram(lar): <code>{', '.join(telegrams) if telegrams else 'yo‘q'}</code>\n"
        f"📅 Ro'yxatdan o'tgan: <b>{user.created_at.strftime('%Y-%m-%d %H:%M')}</b>"
    )

    await callback.message.edit_text(
        info_text,
        reply_markup=get_user_manage_kb(user.id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("block_u:"))
async def toggle_block_user(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return await callback.answer("Ruxsat yo'q.", show_alert=True)

    user_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user:
            return await callback.answer("Topilmadi.", show_alert=True)

        user.is_active = not user.is_active
        await db.commit()

    await callback.answer(
        "✅ Foydalanuvchi holati yangilandi.",
        show_alert=True,
    )

    await show_user_detail(callback)


@router.callback_query(F.data.startswith("delete_u:"))
async def confirm_delete(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return await callback.answer("Ruxsat yo'q.", show_alert=True)

    user_id = callback.data.split(":")[1]

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="✅ Ha, o'chirish",
            callback_data=f"force_delete:{user_id}",
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="❌ Bekor qilish",
            callback_data=f"user_info:{user_id}",
        )
    )

    await callback.message.edit_text(
        "⚠️ Foydalanuvchi va unga bog'liq barcha ma'lumotlar o'chadi. Davom etilsinmi?",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("force_delete:"))
async def hard_delete_user(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return await callback.answer("Ruxsat yo'q.", show_alert=True)

    user_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user:
            return await callback.answer("Topilmadi.", show_alert=True)

        await db.delete(user)
        await db.commit()

    await callback.answer("✅ O'chirildi.", show_alert=True)
    await callback.message.delete()


@router.callback_query(F.data == "back_to_users")
async def back_to_list(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return await callback.answer("Ruxsat yo'q.", show_alert=True)

    await manage_users_list(callback.message)
    try:
        await callback.message.delete()
    except Exception:
        pass