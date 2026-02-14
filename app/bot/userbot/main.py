import asyncio
import random
import logging
import os
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, PeerFloodError, SessionPasswordNeededError
from telethon.tl.functions.contacts import AddContactRequest
from groq import AsyncGroq

# ================== KONFIGURATSIYA ==================
API_ID = 32844127
API_HASH = "680be0244466d6be0195e23c31a9f0f2"
BOT_TOKEN = "7963811812:AAFdN0ho8zU1PWuQhaiSRelBW7JXdpTYCFY"
ADMIN_ID = 7281495879           
ADMIN_USERNAME = "bekime06" 
GROQ_KEY = "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"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "accounts.db")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")

# --- AI PROMPT ---
SYSTEM_PROMPT = """Siz cefr.enwis.uz platformasining aqlli yordamchisisiz. 
Sizning vazifangiz: 
1. CEFR imtihoniga tayyorlanuvchilarga Writing (insho) tahlilida yordam berish.
2. Xatolarni tuzatish va sinonimlar taklif qilish.
3. Foydalanuvchilarni platformada test ishlashga rag'batlantirish.
Javoblar faqat O'ZBEK tilida, professional va do'stona bo'lishi shart."""

active_clients = {}
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_KEY)

class Form(StatesGroup):
    phone = State()
    code = State()
    password = State()
    group = State()
    ad = State()

# ================== BAZA BILAN ISHLASH ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS accounts (
            phone TEXT PRIMARY KEY, 
            ai_status INTEGER DEFAULT 0, 
            ads_status INTEGER DEFAULT 0
        )""")
        await db.execute("CREATE TABLE IF NOT EXISTS groups (group_id TEXT PRIMARY KEY, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS target_users (user_id INTEGER PRIMARY KEY, group_id TEXT, status TEXT DEFAULT 'pending')")
        await db.commit()

# ================== USERBOT ASOSIY MANTIQI ==================
async def run_userbot(phone):
    client = TelegramClient(os.path.join(SESSIONS_DIR, phone), API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            logging.warning(f"Akkaunt avtorizatsiyadan o'tmagan: {phone}")
            return
        active_clients[phone] = client
        logging.info(f"Userbot ishga tushdi: {phone}")
    except Exception as e:
        logging.error(f"Ulanishda xato {phone}: {e}")
        return

    # --- 1-XOLAT: AI JAVOB BERISH ---
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def ai_handler(event):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT ai_status FROM accounts WHERE phone=?", (phone,)) as cur:
                row = await cur.fetchone()
                if not row or row[0] == 0: return

        sender = await event.get_sender()
        if not sender or sender.bot or sender.username == ADMIN_USERNAME: return
        
        try:
            async with client.action(event.chat_id, 'typing'):
                chat = await groq_client.chat.completions.create(
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": event.text}],
                    model="llama-3.3-70b-versatile"
                )
                await event.reply(chat.choices[0].message.content)
        except Exception as e:
            logging.error(f"AI Xatosi ({phone}): {e}")

    # --- 2-XOLAT: REKLAMA YUBORISH (ADS) ---
    async def ads_sender_loop():
        status_msg = None
        sent_local = 0
        while True:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT ads_status FROM accounts WHERE phone=?", (phone,)) as cur:
                    row = await cur.fetchone()
                    if not row or row[0] == 0: 
                        await asyncio.sleep(20); continue

                async with db.execute("SELECT user_id FROM target_users WHERE status='pending' LIMIT 1") as cur:
                    target = await cur.fetchone()
                async with db.execute("SELECT text FROM ads ORDER BY RANDOM() LIMIT 1") as cur_ad:
                    ad = await cur_ad.fetchone()

            if target and ad:
                try:
                    user_id = target[0]
                    # Kontaktga qo'shish (Spam filtrlari uchun)
                    await client(AddContactRequest(id=user_id, first_name="User", last_name="", phone="", add_phone_privacy_exception=False))
                    await asyncio.sleep(3)
                    await client.send_message(user_id, ad[0])
                    
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("UPDATE target_users SET status='sent' WHERE user_id=?", (user_id,))
                        await db.commit()
                    
                    sent_local += 1
                    report = f"🚀 **ADS REPORT ({phone})**\n✅ Yuborildi: {sent_local}\n👤 Target ID: {user_id}"
                    
                    if not status_msg: status_msg = await client.send_message(f"@{ADMIN_USERNAME}", report)
                    else:
                        try: await client.edit_message(f"@{ADMIN_USERNAME}", status_msg.id, report)
                        except: status_msg = await client.send_message(f"@{ADMIN_USERNAME}", report)
                    
                    await asyncio.sleep(random.randint(90, 200)) # Spamga tushmaslik uchun interval
                except (PeerFloodError, FloodWaitError) as e:
                    await client.send_message(f"@{ADMIN_USERNAME}", f"⚠️ {phone} SPAMGA TUSHDI! To'xtatildi.\nKutilishi kerak: {e}")
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("UPDATE accounts SET ads_status=0 WHERE phone=?", (phone,))
                        await db.commit()
                    break
                except Exception:
                    await asyncio.sleep(60)
            else:
                await asyncio.sleep(60)

    # --- 3-XOLAT: SKANER (GRUPPADAN ODAM YIG'ISH) ---
    async def group_scraper():
        while True:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT group_id FROM groups WHERE status='pending' LIMIT 1") as cur:
                    row = await cur.fetchone()
            
            if row:
                group_id = row[0]
                try:
                    entity = await client.get_entity(group_id)
                    collected = 0
                    async for user in client.iter_participants(entity, limit=500):
                        if not user.bot and not user.deleted:
                            async with aiosqlite.connect(DB_PATH) as db:
                                await db.execute("INSERT OR IGNORE INTO target_users (user_id, group_id) VALUES (?, ?)", (user.id, group_id))
                                await db.commit()
                            collected += 1
                    
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("UPDATE groups SET status='done' WHERE group_id=?", (group_id,))
                        await db.commit()
                    await client.send_message(f"@{ADMIN_USERNAME}", f"✅ Skaner tugadi: {group_id}\n👤 {collected} ta user qo'shildi.")
                except Exception as e:
                    logging.error(f"Skaner xatosi: {e}")
            await asyncio.sleep(120)

    asyncio.create_task(ads_sender_loop())
    asyncio.create_task(group_scraper())
    await client.run_until_disconnected()

# ================== ADMIN PANEL (AIOGRAM) ==================
def main_kb():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="📱 Akkauntlarni boshqarish"))
    kb.row(types.KeyboardButton(text="➕ Akkaunt qo'shish"), types.KeyboardButton(text="📊 Statistika"))
    kb.row(types.KeyboardButton(text="📂 Guruhlar"), types.KeyboardButton(text="📝 Matnlar"))
    return kb.as_markup(resize_keyboard=True)

@dp.message(Command("start"), F.from_user.id == ADMIN_ID)
async def cmd_start(message: types.Message):
    await message.answer("🕹 **Boshqaruv markazi**", reply_markup=main_kb())

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT count(*) FROM target_users WHERE status='sent'") as c1: s = (await c1.fetchone())[0]
        async with db.execute("SELECT count(*) FROM target_users WHERE status='pending'") as c2: p = (await c2.fetchone())[0]
        async with db.execute("SELECT count(*) FROM accounts") as c3: a = (await c3.fetchone())[0]
    await message.answer(f"📊 **Statistika:**\n\n✅ Yuborilgan reklamalar: {s}\n⏳ Navbatda: {p}\n📱 Ulangan akkauntlar: {a}")

@dp.message(F.text == "📱 Akkauntlarni boshqarish")
async def list_accs(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT phone, ai_status, ads_status FROM accounts") as cur: rows = await cur.fetchall()
    
    if not rows: return await message.answer("Hali akkauntlar qo'shilmagan.")
    
    for row in rows:
        phone, ai, ads = row
        txt = f"📞 `{phone}`\n🤖 AI: {'✅' if ai else '❌'} | 📢 Ads: {'✅' if ads else '❌'}"
        ib = InlineKeyboardBuilder()
        ib.button(text="🤖 AI On/Off", callback_data=f"tog_ai_{phone}")
        ib.button(text="📢 Ads On/Off", callback_data=f"tog_ads_{phone}")
        ib.button(text="🗑 O'chirish", callback_data=f"rem_acc_{phone}")
        ib.adjust(2, 1)
        await message.answer(txt, reply_markup=ib.as_markup())

@dp.callback_query(F.data.startswith("tog_"))
async def toggler(call: types.CallbackQuery):
    _, mode, phone = call.data.split("_")
    col = "ai_status" if mode == "ai" else "ads_status"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE accounts SET {col} = 1 - {col} WHERE phone=?", (phone,))
        await db.commit()
    await call.answer("O'zgarish saqlandi.")
    await call.message.delete()
    await list_accs(call.message)

@dp.callback_query(F.data.startswith("rem_acc_"))
async def remover(call: types.CallbackQuery):
    phone = call.data.split("_")[2]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM accounts WHERE phone=?", (phone,))
        await db.commit()
    if phone in active_clients:
        await active_clients[phone].disconnect()
        del active_clients[phone]
    path = os.path.join(SESSIONS_DIR, f"{phone}.session")
    if os.path.exists(path): os.remove(path)
    await call.answer("Akkaunt o'chirildi."); await call.message.delete()

# --- AKKAUNT QO'SHISH JARAYONI ---
@dp.message(F.text == "➕ Akkaunt qo'shish")
async def add_a_start(message: types.Message, state: FSMContext):
    await message.answer("Raqamni kiriting (+998901234567):")
    await state.set_state(Form.phone)

@dp.message(Form.phone)
async def add_a_ph(message: types.Message, state: FSMContext):
    ph = message.text.replace(" ", "")
    cl = TelegramClient(os.path.join(SESSIONS_DIR, ph), API_ID, API_HASH)
    await cl.connect()
    try:
        s = await cl.send_code_request(ph)
        await state.update_data(phone=ph, client=cl, hash=s.phone_code_hash)
        await message.answer("Kodni yuboring:"); await state.set_state(Form.code)
    except Exception as e: await message.answer(f"Xato: {e}"); await state.clear()

@dp.message(Form.code)
async def add_a_cd(message: types.Message, state: FSMContext):
    d = await state.get_data()
    try:
        await d['client'].sign_in(d['phone'], message.text, phone_code_hash=d['hash'])
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO accounts (phone) VALUES (?, 0, 0)", (d['phone'],))
            await db.commit()
        asyncio.create_task(run_userbot(d['phone']))
        await message.answer(f"✅ {d['phone']} muvaffaqiyatli ulandi!"); await state.clear()
    except SessionPasswordNeededError:
        await message.answer("2FA parolni yuboring:"); await state.set_state(Form.password)
    except Exception as e: await message.answer(f"Xato: {e}")

@dp.message(Form.password)
async def add_a_ps(message: types.Message, state: FSMContext):
    d = await state.get_data()
    try:
        await d['client'].sign_in(password=message.text)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO accounts (phone) VALUES (?, 0, 0)", (d['phone'],))
            await db.commit()
        asyncio.create_task(run_userbot(d['phone']))
        await message.answer("✅ 2FA orqali ulandi!"); await state.clear()
    except Exception as e: await message.answer(f"Parol xato: {e}")

# --- GURUHLAR VA MATNLAR ---
@dp.message(F.text == "📂 Guruhlar")
async def m_groups(message: types.Message):
    ib = InlineKeyboardBuilder()
    ib.button(text="➕ Guruh qo'shish", callback_data="add_grp")
    await message.answer("Skaner guruhlari (Odam yig'ish uchun):", reply_markup=ib.as_markup())

@dp.callback_query(F.data == "add_grp")
async def add_g_call(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Guruh username yoki ID sini yuboring:"); await state.set_state(Form.group)

@dp.message(Form.group)
async def save_g(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO groups (group_id) VALUES (?)", (message.text,))
        await db.commit()
    await message.answer("✅ Guruh navbatga qo'shildi."); await state.clear()

@dp.message(F.text == "📝 Matnlar")
async def m_ads(message: types.Message):
    ib = InlineKeyboardBuilder()
    ib.button(text="➕ Yangi matn", callback_data="add_ad")
    await message.answer("Reklama matnlari bazasi:", reply_markup=ib.as_markup())

@dp.callback_query(F.data == "add_ad")
async def add_a_call(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Reklama matnini yuboring:"); await state.set_state(Form.ad)

@dp.message(Form.ad)
async def save_a(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO ads (text) VALUES (?)", (message.text,))
        await db.commit()
    await message.answer("✅ Matn saqlandi."); await state.clear()

# ================== STARTUP ==================
async def main():
    if not os.path.exists(SESSIONS_DIR): os.makedirs(SESSIONS_DIR)
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT phone FROM accounts") as cur: accs = await cur.fetchall()
    for a in accs: asyncio.create_task(run_userbot(a[0]))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())