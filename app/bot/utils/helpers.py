import random
import re
from hashlib import sha256
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

# Shu qiymatlarni configdan olganing yaxshi
REQUIRED_CHANNELS = [
    "@enwis_uz",
]

ADMIN_IDS = {
    7281495879,  # o'zingning telegram id'ing
}


def normalize_phone(phone: str) -> str:
    """
    Telefon raqamni yagona formatga keltiradi.
    Natija: 998XXXXXXXXX
    """
    digits = re.sub(r"\D", "", phone or "")

    if digits.startswith("998") and len(digits) == 12:
        return digits

    if digits.startswith("8") and len(digits) == 9:
        return f"998{digits}"

    if len(digits) == 9:
        return f"998{digits}"

    return digits


def generate_otp(length: int = 6) -> str:
    return "".join(random.choices("0123456789", k=length))


def hash_code(code: str) -> str:
    return sha256(code.encode("utf-8")).hexdigest()


async def check_subscription(bot: Bot, user_id: int) -> bool:
    """
    Foydalanuvchi barcha required kanallarga a'zo ekanini tekshiradi.
    """
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except TelegramBadRequest:
            return False
    return True


async def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS