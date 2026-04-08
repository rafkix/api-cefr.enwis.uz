from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_sub_keyboard(args: str | None = None) -> InlineKeyboardMarkup:
    callback_data = f"check_sub:{args}" if args else "check_sub:None"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Kanalga o'tish",
                    url="https://t.me/enwis_uz",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Obunani tekshirish",
                    callback_data=callback_data,
                )
            ],
        ]
    )


def get_user_manage_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔒 Bloklash / Ochish",
                    callback_data=f"block_u:{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 O'chirish",
                    callback_data=f"delete_u:{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Orqaga",
                    callback_data="back_to_users",
                )
            ],
        ]
    )