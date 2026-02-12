import random
from aiogram import Bot

REQUIRED_CHANNEL = "@enwis_uz"
ADMINS = [7281495879, 6813390517]

async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception:
        return False

def normalize_phone(phone: str) -> str:
    cleaned = "".join(filter(str.isdigit, phone))
    if cleaned.startswith("8"): cleaned = "998" + cleaned[1:]
    if not cleaned.startswith("998") and len(cleaned) == 9:
        cleaned = "998" + cleaned
    return f"+{cleaned}"

def generate_otp() -> str:
    return "".join([str(random.randint(0, 9)) for _ in range(6)])

async def is_admin(user_id: int) -> bool:
    return user_id in ADMINS