import asyncio
import os
import sys
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload

# Loyiha root papkasini qo'shish (Pathlarni to'g'irlash)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password

# Modellar
from app.modules.auth.models import (
    User, UserContact, UserIdentity, VerificationCode, 
    VerificationPurpose, AuthProvider, UserRole
)

# ================= KONFIGURATSIYA =================
REQUIRED_CHANNEL = "@enwis_uz" 
# app/core/config.py faylingizda ADMIN_IDS = [1234567, 8901234] kabi ro'yxat bo'lishi kerak
ADMINS = [561234567]  # O'zingizning Telegram ID'ingizni yozing yoki settings.ADMIN_IDS dan oling

class AdminStates(StatesGroup):
    waiting_broadcast_text = State()
    waiting_user_search = State()

# ================= HOLATLAR (FSM) =================
class AuthFlow(StatesGroup):
    waiting_contact_login = State()    # Saytga kirish uchun kod kutish
    waiting_contact_verify = State()   # Telegramni profilga bog'lash
    waiting_contact_forgot = State()   # Parolni unutganda tiklash
    waiting_contact_password = State() # Profil ichidan parolni o'zgartirish
    waiting_new_password = State()     # Yangi parolni yozish jarayoni

# ================= BOTNI SOZLASH =================
bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================= YORDAMCHI FUNKSIYALAR =================
async def check_subscription(user_id: int) -> bool:
    """Foydalanuvchi majburiy kanalda borligini tekshirish"""
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

# ================= KLAVIATURALAR =================
def get_main_keyboard():
    kb = [
        [types.KeyboardButton(text="🔑 Parolni o'zgartirish")],
        [types.KeyboardButton(text="ℹ️ Profil ma'lumotlari")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_contact_keyboard():
    kb = [[types.KeyboardButton(text="📱 Kontaktni yuborish", request_contact=True)]]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_sub_keyboard(args=None):
    """Obuna bo'lish tugmalari"""
    cb_data = f"check_sub:{args}" if args else "check_sub"
    buttons = [
        [types.InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
        [types.InlineKeyboardButton(text="🔄 Obunani tekshirish", callback_data=cb_data)]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_keyboard():
    kb = [
        [types.KeyboardButton(text="📊 Statistika"), types.KeyboardButton(text="👥 Foydalanuvchilarni boshqarish")],
        [types.KeyboardButton(text="📢 Xabar yuborish"), types.KeyboardButton(text="🏠 Asosiy menyu")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ================= HANDLERLAR =================

@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    args = command.args

    # 1. Obuna tekshiruvi
    if not await check_subscription(message.from_user.id):
        return await message.answer(
            f"👋 <b>Xush kelibsiz!</b>\n\nBot xizmatlaridan foydalanish uchun {REQUIRED_CHANNEL} kanalimizga a'zo bo'lishingiz kerak.",
            reply_markup=get_sub_keyboard(args)
        )

    # 2. Parolni unutganlar uchun (t.me/bot?start=forgot_password)
    if args == "forgot_password":
        await state.set_state(AuthFlow.waiting_contact_forgot)
        return await message.answer(
            "🔐 <b>Parolni tiklash</b>\n\nHisobingizni tasdiqlash uchun pastdagi tugmani bosing:",
            reply_markup=get_contact_keyboard()
        )

    # 3. Login uchun kelgan bo'lsa (t.me/bot?start=998...)
    if args and (args.isdigit() or args.startswith("998")):
        phone = normalize_phone(args)
        await state.update_data(login_phone=phone)
        await state.set_state(AuthFlow.waiting_contact_login)
        return await message.answer(
            f"🔐 <b>Kirish tizimi</b>\n\n{phone} raqamingizni tasdiqlash uchun kontaktingizni yuboring:",
            reply_markup=get_contact_keyboard()
        )

    # 4. Telegramni bog'lash (t.me/bot?start=verify_phone)
    if args == "verify_phone":
        await state.set_state(AuthFlow.waiting_contact_verify)
        return await message.answer(
            "🔗 <b>Telegramni bog'lash</b>\n\nHisobingizni tasdiqlash uchun kontaktingizni yuboring:",
            reply_markup=get_contact_keyboard()
        )

    await message.answer(
        f"👋 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\nEnwis Hub xizmatiga xush kelibsiz.",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data.startswith("check_sub"))
async def process_check_sub(callback: types.CallbackQuery, state: FSMContext):
    """Obunani tekshirish tugmasi"""
    is_sub = await check_subscription(callback.from_user.id)
    if is_sub:
        await callback.answer("✅ Rahmat! Obuna tasdiqlandi.")
        data_parts = callback.data.split(":")
        args = data_parts[1] if len(data_parts) > 1 else None
        
        await callback.message.delete()
        fake_command = CommandObject(args=args, command="start")
        await cmd_start(callback.message, fake_command, state)
    else:
        await callback.answer("❌ Siz hali kanalga a'zo emassiz!", show_alert=True)

# --- LOGIN PROTSESSI ---
@dp.message(AuthFlow.waiting_contact_login, F.contact)
async def process_login_contact(message: types.Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        return await message.answer("❌ Faqat o'z kontaktingizni yuboring.")

    contact_phone = normalize_phone(message.contact.phone_number)
    data = await state.get_data()
    expected_phone = data.get("login_phone")

    if expected_phone and contact_phone != expected_phone:
        return await message.answer(f"❌ Xato! Siz saytda {expected_phone} raqamini kiritgansiz.")

    async with AsyncSessionLocal() as db:
        stmt = select(UserContact).where(UserContact.value == contact_phone)
        contact_obj = (await db.execute(stmt)).scalar_one_or_none()

        if not contact_obj:
            return await message.answer("❌ Bu raqam tizimda topilmadi. Avval ro'yxatdan o'ting.")

        otp_code = generate_otp()
        new_code = VerificationCode(
            user_id=contact_obj.user_id,
            target=contact_phone,
            code=otp_code,
            purpose=VerificationPurpose.LOGIN,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            is_used=False
        )
        db.add(new_code)
        await db.commit()

        await message.answer(f"✅ Tasdiqlandi!\n\nKirish kodingiz: <code>{otp_code}</code>")
    await state.clear()

# --- PAROLNI UNUTGANLAR UCHUN ---
@dp.message(AuthFlow.waiting_contact_forgot, F.contact)
async def process_forgot_contact(message: types.Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id: return

    phone = normalize_phone(message.contact.phone_number)
    async with AsyncSessionLocal() as db:
        stmt = select(UserContact).where(UserContact.value == phone)
        contact_obj = (await db.execute(stmt)).scalar_one_or_none()

        if not contact_obj:
            return await message.answer("❌ Bu raqam tizimda ro'yxatdan o'tmagan.")

        await state.update_data(target_user_id=contact_obj.user_id)
        await state.set_state(AuthFlow.waiting_new_password)
        await message.answer("🔓 <b>Hisob tasdiqlandi. Yangi parolingizni kiriting:</b>", reply_markup=types.ReplyKeyboardRemove())

# --- PAROLNI O'ZGARTIRISH (PROFIL ICHIDAN) ---
@dp.message(F.text == "🔑 Parolni o'zgartirish")
async def start_change_pw(message: types.Message, state: FSMContext):
    if not await check_subscription(message.from_user.id):
        return await message.answer("⚠️ Kanalga obuna bo'lish shart!")
    
    await state.set_state(AuthFlow.waiting_contact_password)
    await message.answer("Xavfsizlik uchun kontaktingizni yuboring:", reply_markup=get_contact_keyboard())

@dp.message(AuthFlow.waiting_contact_password, F.contact)
async def check_pw_contact(message: types.Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id: return
    
    tg_id = str(message.from_user.id)
    async with AsyncSessionLocal() as db:
        stmt = select(UserIdentity).where(UserIdentity.provider_id == tg_id, UserIdentity.provider == AuthProvider.TELEGRAM)
        identity = (await db.execute(stmt)).scalar_one_or_none()

        if not identity:
            return await message.answer("❌ Avval profilingizni bog'lang.")

        await state.update_data(target_user_id=identity.user_id)
        await state.set_state(AuthFlow.waiting_new_password)
        await message.answer("🔓 <b>Yangi parolingizni kiriting:</b>", reply_markup=types.ReplyKeyboardRemove())

# --- YANGI PAROLNI SAQLASH ---
@dp.message(AuthFlow.waiting_new_password)
async def save_new_pw(message: types.Message, state: FSMContext):
    if not message.text or len(message.text) < 6:
        return await message.answer("⚠️ Parol kamida 6 ta belgidan iborat bo'lsin!")

    data = await state.get_data()
    uid = data.get("target_user_id")
    new_hash = hash_password(message.text[:70])

    async with AsyncSessionLocal() as db:
        stmt = update(UserIdentity).where(
            and_(UserIdentity.user_id == uid, UserIdentity.provider == AuthProvider.LOCAL)
        ).values(password_hash=new_hash)
        await db.execute(stmt)
        await db.commit()

    await message.answer("✅ Parol muvaffaqiyatli yangilandi!", reply_markup=get_main_keyboard())
    await state.clear()

# --- VERIFY PROTSESSI ---
@dp.message(AuthFlow.waiting_contact_verify, F.contact)
async def process_verify_contact(message: types.Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id: return
    contact_phone = normalize_phone(message.contact.phone_number)
    tg_id = str(message.from_user.id)

    async with AsyncSessionLocal() as db:
        stmt = select(UserContact).where(UserContact.value == contact_phone)
        contact_obj = (await db.execute(stmt)).scalar_one_or_none()

        if not contact_obj:
            return await message.answer("❌ Bu raqam saytda mavjud emas.")

        id_stmt = select(UserIdentity).where(UserIdentity.user_id == contact_obj.user_id, UserIdentity.provider == AuthProvider.TELEGRAM)
        identity = (await db.execute(id_stmt)).scalar_one_or_none()

        if not identity:
            db.add(UserIdentity(user_id=contact_obj.user_id, provider=AuthProvider.TELEGRAM, provider_id=tg_id))
        else:
            identity.provider_id = tg_id
        
        contact_obj.is_verified = True
        await db.commit()
        await message.answer("✅ Telegram bog'landi!", reply_markup=get_main_keyboard())
    await state.clear()

# --- PROFIL MA'LUMOTLARI ---
@dp.message(F.text == "ℹ️ Profil ma'lumotlari")
async def show_profile(message: types.Message):
    if not await check_subscription(message.from_user.id): return
    tg_id = str(message.from_user.id)
    async with AsyncSessionLocal() as db:
        stmt = select(UserIdentity).where(UserIdentity.provider_id == tg_id, UserIdentity.provider == AuthProvider.TELEGRAM)
        identity = (await db.execute(stmt)).scalar_one_or_none()
        if not identity:
            return await message.answer("❌ Profil bog'lanmagan.")

        user_stmt = select(User).options(selectinload(User.profile), selectinload(User.contacts)).where(User.id == identity.user_id)
        user = (await db.execute(user_stmt)).scalar_one_or_none()
        if user:
            contacts = "\n".join([f"• {c.value}" for c in user.contacts])
            await message.answer(f"👤 <b>Profil:</b> {user.profile.full_name}\n🆔 ID: <code>{user.id}</code>\n📞 Raqamlar:\n{contacts}")

async def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

@dp.message(F.text == "/admin")
async def admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await message.answer("🛠 <b>Admin paneliga xush kelibsiz!</b>", reply_markup=get_admin_keyboard())

# --- STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if not await is_admin(message.from_user.id): return
    
    async with AsyncSessionLocal() as db:
        # Jami foydalanuvchilar
        total_users = (await db.execute(select(User))).scalars().all()
        # Telegram bog'laganlar
        tg_linked = (await db.execute(select(UserIdentity).where(UserIdentity.provider == AuthProvider.TELEGRAM))).scalars().all()
        # Oxirgi 24 soatda qo'shilganlar
        last_24h = datetime.utcnow() - timedelta(days=1)
        new_users = (await db.execute(select(User).where(User.created_at >= last_24h))).scalars().all()

        text = (
            "📈 <b>Bot statistikasi:</b>\n\n"
            f"👤 Jami foydalanuvchilar: <b>{len(total_users)} ta</b>\n"
            f"🔗 Telegram bog'langan: <b>{len(tg_linked)} ta</b>\n"
            f"✨ Yangi (24 soat): <b>{len(new_users)} ta</b>"
        )
        await message.answer(text)

# --- REKLAMA / XABAR YUBORISH ---
@dp.message(F.text == "📢 Xabar yuborish")
async def start_broadcast(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(AdminStates.waiting_broadcast_text)
    await message.answer("Xabarni kiriting (rasm, matn yoki video):", reply_markup=types.ReplyKeyboardRemove())

@dp.message(AdminStates.waiting_broadcast_text)
async def process_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as db:
        # Faqat telegrami bor foydalanuvchilarni olish
        stmt = select(UserIdentity).where(UserIdentity.provider == AuthProvider.TELEGRAM)
        users = (await db.execute(stmt)).scalars().all()
        
        count = 0
        await message.answer(f"🚀 Xabar yuborish boshlandi ({len(users)} kishiga)...")
        
        for user in users:
            try:
                await bot.copy_message(
                    chat_id=int(user.provider_id),
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
                count += 1
                await asyncio.sleep(0.05) # Telegram limitidan oshmaslik uchun
            except Exception:
                continue
        
        await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yetkazildi.", reply_markup=get_admin_keyboard())

# --- FOYDALANUVCHINI QIDIRISH ---
@dp.message(F.text == "👥 Foydalanuvchilarni boshqarish")
async def manage_users(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(AdminStates.waiting_user_search)
    await message.answer("Qidirish uchun foydalanuvchi telefon raqamini yoki ID sini yozing:")

@dp.message(AdminStates.waiting_user_search)
async def search_user(message: types.Message, state: FSMContext):
    async with AsyncSessionLocal() as db:
        search = message.text
        if search.startswith("+"): search = search[1:]
        
        # Telefon yoki ID bo'yicha qidirish
        stmt = select(User).join(UserContact).where(
            (UserContact.value.contains(search)) | (User.id.cast(types.String) == search)
        ).options(selectinload(User.profile), selectinload(User.contacts))
        
        user = (await db.execute(stmt)).scalar_one_or_none()
        
        if not user:
            return await message.answer("❌ Foydalanuvchi topilmadi.")
        
        contacts = "\n".join([f"• {c.value}" for c in user.contacts])
        text = (
            f"👤 <b>Foydalanuvchi:</b> {user.profile.full_name}\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"📅 Ro'yxatdan o'tdi: {user.created_at.strftime('%Y-%m-%d')}\n"
            f"📞 Kontaktlar:\n{contacts}"
        )
        
        # Bloklash yoki o'chirish tugmalari (Inline)
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🗑 O'chirish (DB dan)", callback_data=f"delete_u:{user.id}")]
        ])
        
        await message.answer(text, reply_markup=kb)
        await state.clear()

@dp.message(F.text == "🏠 Asosiy menyu")
async def back_to_main(message: types.Message):
    await message.answer("Bosh menyu:", reply_markup=get_main_keyboard())

# --- O'CHIRISH FUNKSIYASI ---
@dp.callback_query(F.data.startswith("delete_u:"))
async def delete_user_callback(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as db:
        # Userni o'chirish (Cascade o'chadi agar modellar to'g'ri sozlangan bo'lsa)
        await db.execute(update(User).where(User.id == uid).values(is_active=False)) # O'chirish o'rniga nofaol qilish xavfsizroq
        await db.commit()
        await callback.answer("✅ Foydalanuvchi tizimda nofaol qilindi.", show_alert=True)
        await callback.message.delete()

# ================= ASOSIY ISHGA TUSHIRISH =================
async def main():
    print("🚀 Enwis Auth Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to'xtatildi")