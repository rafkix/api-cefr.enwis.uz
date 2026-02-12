from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_sub_keyboard(args=None):
    cb_data = f"check_sub:{args}" if args else "check_sub"
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url="https://t.me/enwis_uz"))
    builder.row(types.InlineKeyboardButton(text="🔄 Obunani tekshirish", callback_data=cb_data))
    return builder.as_markup()

def get_user_manage_kb(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🛡 Rol", callback_data=f"edit_role:{user_id}"),
        types.InlineKeyboardButton(text="🔑 Reset PW", callback_data=f"reset_pw:{user_id}")
    )
    builder.row(
        types.InlineKeyboardButton(text="🚫 Bloklash", callback_data=f"block_u:{user_id}"),
        types.InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"delete_u:{user_id}")
    )
    builder.row(types.InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_users"))
    return builder.as_markup()