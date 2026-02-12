from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

from app.core.database import AsyncSessionLocal
from app.modules.auth.models import User, UserIdentity, AuthProvider
from app.bot.utils.helpers import is_admin
from app.bot.keyboards.reply import get_admin_keyboard, get_main_keyboard
from app.bot.keyboards.inline import get_user_manage_kb
from app.bot.states.states import AdminStates

router = Router()

@router.message(F.text == "/admin")
async def admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await message.answer("🛠 Admin panel:", reply_markup=get_admin_keyboard())

@router.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if not await is_admin(message.from_user.id): return
    async with AsyncSessionLocal() as db:
        total = len((await db.execute(select(User))).scalars().all())
        tg_cnt = len((await db.execute(select(UserIdentity).where(UserIdentity.provider == AuthProvider.TELEGRAM))).scalars().all())
        await message.answer(f"📈 Jami: {total}\n🔗 Telegram: {tg_cnt}")

@router.message(F.text == "👥 Foydalanuvchilarni boshqarish")
async def manage_users_list(message: types.Message):
    if not await is_admin(message.from_user.id): return
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).options(selectinload(User.profile)).limit(10))).scalars().all()
        builder = InlineKeyboardBuilder()
        for u in users:
            builder.row(types.InlineKeyboardButton(text=f"👤 {u.profile.full_name if u.profile else u.id}", callback_data=f"user_info:{u.id}"))
        builder.row(types.InlineKeyboardButton(text="🔍 Qidirish", callback_data="search_user_start"))
        await message.answer("Foydalanuvchilar:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("user_info:"))
async def show_user_detail(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        # Foydalanuvchini barcha bog'liqliklari bilan yuklaymiz
        result = await db.execute(
            select(User).options(selectinload(User.profile)).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return await callback.answer("Foydalanuvchi topilmadi.")

        status = "🔴 Bloklangan" if user.is_active is False else "🟢 Faol"
        role = user.role if hasattr(user, 'role') else "User"
        
        info_text = (
            f"👤 **Foydalanuvchi ma'lumotlari:**\n\n"
            f"🆔 ID: `{user.id}`\n"
            f"📝 Ism: {user.profile.full_name if user.profile else 'Noma'lum'}\n"
            f"🎭 Rol: `{role}`\n"
            f"📊 Holati: {status}\n"
            f"📅 Ro'yxatdan o'tdi: {user.created_at.strftime('%Y-%m-%d')}"
        )
        
        await callback.message.edit_text(
            info_text, 
            reply_markup=get_user_manage_kb(user.id),
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith("block_u:"))
async def toggle_block_user(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user:
            # Holatni teskarisiga o'zgartiramiz
            user.is_active = not user.is_active
            await db.commit()
            status_msg = "bloklandi" if not user.is_active else "blokdan ochildi"
            await callback.answer(f"✅ Foydalanuvchi {status_msg}!", show_alert=True)
            # Ma'lumotni yangilaymiz
            await show_user_detail(callback)

@router.callback_query(F.data.startswith("delete_u:"))
async def confirm_delete(callback: types.CallbackQuery):
    user_id = callback.data.split(":")[1]
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="✅ Ha, butunlay o'chirish", callback_data=f"force_delete:{user_id}"))
    builder.row(types.InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"user_info:{user_id}"))
    await callback.message.edit_text("⚠️ Diqqat! Foydalanuvchi va barcha natijalari o'chadi. Rozimisiz?", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("force_delete:"))
async def hard_delete_user(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user:
            await db.delete(user)
            await db.commit()
            await callback.answer("✅ O'chirildi!", show_alert=True)
            await callback.message.delete()
        else:
            await callback.answer("Topilmadi.")
            
@router.callback_query(F.data == "back_to_users")
async def back_to_list(callback: types.CallbackQuery):
    await manage_users_list(callback.message)
    await callback.message.delete()