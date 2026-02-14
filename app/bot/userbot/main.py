import asyncio
import random
import logging
import os
import sqlite3
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, PeerFloodError, UserPrivacyRestrictedError
from groq import AsyncGroq

# --- KONFIGURATSIYA ---
API_ID = 32844127
API_HASH = "680be0244466d6be0195e23c31a9f0f2"
BOT_TOKEN = "7963811812:AAFdN0ho8zU1PWuQhaiSRelBW7JXdpTYCFY"
ADMIN_ID = 7281495879  
GROQ_KEY = "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"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "accounts.db")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
SENT_USERS_FILE = os.path.join(BASE_DIR, "sent_users.txt")

# Global holat
IS_ADVERTISING = False 
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_KEY)

class Form(StatesGroup):
    phone, code, group, ad = State(), State(), State(), State()

# ================== FAYL BILAN ISHLASH ==================
def get_sent_users_from_file():
    if not os.path.exists(SENT_USERS_FILE):
        return set()
    with open(SENT_USERS_FILE, "r") as f:
        return set(line.strip() for line in f)

def save_user_to_file(user_id):
    with open(SENT_USERS_FILE, "a") as f:
        f.write(f"{user_id}\n")

# ================== BAZA BILAN ISHLASH ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS accounts (
            phone TEXT PRIMARY KEY, api_id INTEGER, api_hash TEXT, status TEXT DEFAULT 'active')""")
        await db.execute("""CREATE TABLE IF NOT EXISTS groups (
            group_id INTEGER PRIMARY KEY, status TEXT DEFAULT 'pending')""")
        await db.execute("CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)")
        await db.execute("""CREATE TABLE IF NOT EXISTS target_users (
            user_id INTEGER PRIMARY KEY, status TEXT DEFAULT 'pending')""")
        await db.commit()

# ================== USERBOT MANTIQI ==================
async def run_userbot(phone, api_id, api_hash):
    global IS_ADVERTISING
    client = TelegramClient(os.path.join(SESSIONS_DIR, phone), api_id, api_hash)
    await client.start()

    # 1. Scraper
    async def scrape_task():
        while True:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT group_id FROM groups WHERE status='pending' LIMIT 1") as cur:
                    group = await cur.fetchone()
            
            if group:
                gid = group[0]
                try:
                    entity = await client.get_entity(gid)
                    sent_list = get_sent_users_from_file() # Fayldagilarni olish
                    count = 0
                    async for user in client.iter_participants(entity, limit=5000):
                        if not user.bot and not user.deleted and str(user.id) not in sent_list:
                            async with aiosqlite.connect(DB_PATH) as db:
                                await db.execute("INSERT OR IGNORE INTO target_users (user_id) VALUES (?)", (user.id,))
                                await db.commit()
                            count += 1
                    
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("UPDATE groups SET status='scraped' WHERE group_id=?", (gid,))
                        await db.commit()
                    await bot.send_message(ADMIN_ID, f"✅ Scraper ({phone}): `{gid}` guruhidan {count} ta yangi user yig'ildi.")
                except Exception as e: logging.error(f"Scrape error: {e}")
            await asyncio.sleep(60)

    # 2. Ad Sender (Random matn + File check)
    async def ad_sender_task():
        global IS_ADVERTISING
        while True:
            if not IS_ADVERTISING:
                await asyncio.sleep(5); continue

            # Fayldan oxirgi ro'yxatni o'qish
            sent_list = get_sent_users_from_file()

            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT user_id FROM target_users WHERE status='pending' LIMIT 50") as cur:
                    targets = await cur.fetchall()
                async with db.execute("SELECT text FROM ads ORDER BY RANDOM() LIMIT 1") as cur_ad:
                    ad = await cur_ad.fetchone()

            if targets and ad:
                # Ro'yxatdan haqiqatdan ham yuborilmaganini topish
                target_id = None
                for t in targets:
                    if str(t[0]) not in sent_list:
                        target_id = t[0]
                        break
                
                if target_id:
                    try:
                        await client.send_message(target_id, ad[0])
                        # Bazada belgilash
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute("UPDATE target_users SET status='sent' WHERE user_id=?", (target_id,))
                            await db.commit()
                        # Faylga yozish
                        save_user_to_file(target_id)
                        
                        logging.info(f"🚀 {phone} yubordi: {target_id}")
                        await asyncio.sleep(random.randint(150, 350))
                    except (PeerFloodError, FloodWaitError):
                        await bot.send_message(ADMIN_ID, f"⚠️ SPAM: `{phone}` to'xtadi.")
                        return
                    except Exception:
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute("UPDATE target_users SET status='error' WHERE user_id=?", (target_id,))
                            await db.commit()
                else:
                    await asyncio.sleep(10)
            else:
                await asyncio.sleep(30)

    asyncio.create_task(scrape_task())
    asyncio.create_task(ad_sender_task())
    await client.run_until_disconnected()

# ================== ADMIN BOT (AIOGRAM) ==================
@dp.message(Command("start"), F.from_user.id == ADMIN_ID)
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="🚀 Reklamani Yoqish"), types.KeyboardButton(text="⛔ To'xtatish")],
        [types.KeyboardButton(text="➕ Akkaunt"), types.KeyboardButton(text="📢 Guruh"), types.KeyboardButton(text="📝 Matn")],
        [types.KeyboardButton(text="📊 Statistika")]
    ]
    markup = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("🛠 Boshqaruv", reply_markup=markup)

@dp.message(F.text == "🚀 Reklamani Yoqish")
async def start_ads(message: types.Message):
    global IS_ADVERTISING
    IS_ADVERTISING = True
    await message.answer("✅ Reklama yoqildi.")

@dp.message(F.text == "⛔ To'xtatish")
async def stop_ads(message: types.Message):
    global IS_ADVERTISING
    IS_ADVERTISING = False
    await message.answer("🛑 Reklama to'xtatildi.")

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    sent_f_count = len(get_sent_users_from_file())
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT count(*) FROM target_users WHERE status='pending'") as c1:
            pending = (await c1.fetchone())[0]
    await message.answer(f"📈 **Statistika:**\n\n✅ Yuborilganlar (Faylda): {sent_f_count}\n⌛ Navbatda (Bazada): {pending}")

# --- Akkaunt, Guruh, Matn qo'shish (Oldingi mantiq) ---
@dp.message(F.text == "➕ Akkaunt")
async def add_acc_init(message: types.Message, state: FSMContext):
    await message.answer("📞 Raqam: +998...")
    await state.set_state(Form.phone)

@dp.message(Form.phone)
async def get_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    client = TelegramClient(os.path.join(SESSIONS_DIR, phone), API_ID, API_HASH)
    await client.connect()
    await client.send_code_request(phone)
    await state.update_data(phone=phone, client=client)
    await message.answer("📩 Kod:")
    await state.set_state(Form.code)

@dp.message(Form.code)
async def get_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        await data['client'].sign_in(data['phone'], message.text.strip())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO accounts VALUES (?, ?, ?, 'active')", (data['phone'], API_ID, API_HASH))
            await db.commit()
        await message.answer("✅ Akkaunt qo'shildi!")
        asyncio.create_task(run_userbot(data['phone'], API_ID, API_HASH))
    except Exception as e: await message.answer(f"❌ Xato: {e}")
    finally: await state.clear()

@dp.message(F.text == "📢 Guruh")
async def add_group_init(message: types.Message, state: FSMContext):
    await message.answer("Guruh ID:")
    await state.set_state(Form.group)

@dp.message(Form.group)
async def save_group(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO groups (group_id) VALUES (?)", (int(message.text),))
        await db.commit()
    await message.answer("✅ Guruh qo'shildi.")
    await state.clear()

@dp.message(F.text == "📝 Matn")
async def add_ad_init(message: types.Message, state: FSMContext):
    await message.answer("Matn:")
    await state.set_state(Form.ad)

@dp.message(Form.ad)
async def save_ad(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO ads (text) VALUES (?)", (message.text,))
        await db.commit()
    await message.answer("✅ Matn saqlandi.")
    await state.clear()

async def main():
    if not os.path.exists(SESSIONS_DIR): os.makedirs(SESSIONS_DIR)
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT phone, api_id, api_hash FROM accounts WHERE status='active'") as cur:
            accounts = await cur.fetchall()
    for acc in accounts:
        asyncio.create_task(run_userbot(acc[0], acc[1], acc[2]))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())