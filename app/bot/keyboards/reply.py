from aiogram import types

def get_main_keyboard():
    kb = [
        [types.KeyboardButton(text="🔑 Parolni o'zgartirish")],
        [types.KeyboardButton(text="ℹ️ Profil ma'lumotlari")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_contact_keyboard():
    kb = [[types.KeyboardButton(text="📱 Kontaktni yuborish", request_contact=True)]]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_admin_keyboard():
    kb = [
        [types.KeyboardButton(text="📊 Statistika"), types.KeyboardButton(text="👥 Foydalanuvchilarni boshqarish")],
        [types.KeyboardButton(text="📢 Xabar yuborish"), types.KeyboardButton(text="🏠 Asosiy menyu")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)