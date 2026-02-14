import asyncio
import random
import logging
import os
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, PeerFloodError, SessionPasswordNeededError, UserPrivacyRestrictedError
from telethon.tl.functions.contacts import AddContactRequest
from groq import AsyncGroq

# --- KONFIGURATSIYA ---
API_ID = 32844127
API_HASH = "680be0244466d6be0195e23c31a9f0f2"
BOT_TOKEN = "7963811812:AAFdN0ho8zU1PWuQhaiSRelBW7JXdpTYCFY"
ADMIN_ID = 7281495879           # Botni boshqarish uchun (ID)
ADMIN_USERNAME = "@bekime06"  # Userbot hisobotlari uchun (Username)
GROQ_KEY = "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"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "accounts.db")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
SENT_USERS_FILE = os.path.join(BASE_DIR, "sent_users.txt")

# Prompt va limit sozlamalari
MIN_DELAY, MAX_DELAY = 250, 450
BATCH_SIZE = 50 
IS_ADVERTISING = False
waiting_for_admin = False
is_paused = False

SYSTEM_PROMPT = """Siz cefr.enwis.uz platformasining aqlli va professional yordamchisisiz. Sizning maqsadingiz foydalanuvchilarga CEFR imtihoniga tayyorlanishda va ingliz tili darajasini oshirishda yaqindan yordam berishdir.

Javob berishda quyidagi tamoyillarga amal qiling:

1. PLATFORMA HAQIDA (Umumiy savollar uchun):
   - Vaqtni tejash: Istalgan joyda, 24/7 online shug'ullanish imkoniyati.
   - Real format: Testlar va interfeys real imtihon atmosferasini to'liq his qildiradi.
   - Bepul resurslar: @enwis_uz Telegram kanalida doimiy bepul testlar va materiallar borligi.
   - Sertifikati borlar uchun: "Sertifikat bor bo'lsa ham, darajani yo'qotmaslik va mahoratni doimiy ravishda sinab turish (maintenance) juda muhim. Platformamiz yangilangan testlar orqali sizga bilimingizni 'fresh' saqlashga yordam beradi".

2. WRITING TAHLILI (Insho yuborilsa):
   - Xatoliklar: Grammatik va punktuatsiya xatolarini aniq ko'rsating.
   - Lug'at (Vocabulary): Lug'at boyligini baholang va takroriy so'zlar o'rniga sinonimlar taklif qiling.
   - Baholash: CEFR mezonlari bo'yicha taxminiy darajani (B1, B2, C1) belgilang.
   - Maslahat: Inshoni yanada yaxshilash uchun kamida 2 ta aniq va foydali maslahat bering.

3. TONA VA USLUB:
   - Doimo muloyim, samimiy va rag'batlantiruvchi tilda gapiring.
   - Javoblar qisqa, tushunarli va faqat o'zbek tilida bo'lishi shart.
   - Har bir foydalanuvchiga potentsial muvaffaqiyat egasi kabi munosabatda bo'ling. 
   
4. Texnik yordam va support xizmati

@enwis_support"""

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

# ================== BAZA ISHLARI ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS accounts (phone TEXT PRIMARY KEY, api_id INTEGER, api_hash TEXT, status TEXT DEFAULT 'active')")
        await db.execute("CREATE TABLE IF NOT EXISTS groups (group_id INTEGER PRIMARY KEY, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS target_users (user_id INTEGER PRIMARY KEY, group_id INTEGER, status TEXT DEFAULT 'pending')")
        await db.commit()

def get_sent_users():
    if not os.path.exists(SENT_USERS_FILE): return set()
    with open(SENT_USERS_FILE, "r") as f:
        return set(line.strip() for line in f)

# ================== USERBOT MANTIQI ==================
async def run_userbot(phone, api_id, api_hash):
    global IS_ADVERTISING, waiting_for_admin, is_paused
    client = TelegramClient(os.path.join(SESSIONS_DIR, phone), api_id, api_hash)
    
    try:
        await client.start()
        status_msg = await client.send_message(ADMIN_USERNAME, f"🚀 **Userbot faol:** `{phone}`\nStatus: Navbat kutmoqda...")
    except Exception as e:
        logging.error(f"Error {phone}: {e}")
        return

    # 1. AI JAVOB BERUVCHI VA ADMIN BUYRUQLARI
    @client.on(events.NewMessage(incoming=True))
    async def on_message(event):
        global IS_ADVERTISING, waiting_for_admin, is_paused
        if not event.is_private: return
        
        sender = await event.get_sender()
        if sender.bot: return

        # Admin buyruqlari (Username orqali)
        if sender.username and f"@{sender.username}" == ADMIN_USERNAME:
            cmd = event.text.lower()
            if "boshla" in cmd:
                waiting_for_admin = False
                await event.reply("▶️ Davom etamiz!")
            elif "to'xtat" in cmd:
                is_paused = True
                await event.reply("⏸ Jarayon 5 daqiqaga to'xtatildi.")
            return

        # Oddiy userlar uchun AI javob
        try:
            async with client.action(event.chat_id, 'typing'):
                chat_completion = await groq_client.chat.completions.create(
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": event.text}],
                    model="llama-3.3-70b-versatile"
                )
                await event.reply(chat_completion.choices[0].message.content)
        except: pass

    # 2. SKANER (SCRAPER)
    async def scraper():
        while True:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT group_id FROM groups WHERE status='pending' LIMIT 1") as cur:
                    row = await cur.fetchone()
            if row:
                gid = row[0]
                try:
                    entity = await client.get_entity(gid)
                    count = 0
                    async for user in client.iter_participants(entity, limit=500):
                        if not user.bot and not user.deleted:
                            async with aiosqlite.connect(DB_PATH) as db:
                                await db.execute("INSERT OR IGNORE INTO target_users (user_id, group_id) VALUES (?, ?)", (user.id, gid))
                            count += 1
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("UPDATE groups SET status='scraped' WHERE group_id=?", (gid,))
                        await db.commit()
                    await client.send_message(ADMIN_USERNAME, f"📂 **Guruh skanerlandi:** `{gid}`\n👤 {count} ta user topildi.")
                except: pass
            await asyncio.sleep(60)

    # 3. REKLAMA TARQATUVCHI (KONTAKTGA QO'SHISH BILAN)
    async def sender():
        global IS_ADVERTISING, waiting_for_admin, is_paused
        sent_count = 0
        while True:
            if not IS_ADVERTISING or is_paused:
                if is_paused: await asyncio.sleep(300); is_paused = False
                await asyncio.sleep(10); continue

            sent_list = get_sent_users()
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT user_id FROM target_users WHERE status='pending' LIMIT 50") as cur:
                    targets = await cur.fetchall()
                async with db.execute("SELECT text FROM ads ORDER BY RANDOM() LIMIT 1") as cur_ad:
                    ad = await cur_ad.fetchone()

            if targets and ad:
                target_id = next((t[0] for t in targets if str(t[0]) not in sent_list), None)
                if target_id:
                    try:
                        # Kontaktga qo'shish
                        try:
                            u_ent = await client.get_entity(target_id)
                            await client(AddContactRequest(
                                id=target_id, first_name=u_ent.first_name or "User",
                                last_name="", phone='', add_phone_privacy_exception=False
                            ))
                            await asyncio.sleep(2)
                        except: pass

                        # Xabar yuborish
                        await client.send_message(target_id, ad[0])
                        
                        # Bazaga saqlash
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute("UPDATE target_users SET status='sent' WHERE user_id=?", (target_id,))
                            await db.commit()
                        with open(SENT_USERS_FILE, "a") as f: f.write(f"{target_id}\n")
                        
                        sent_count += 1
                        if sent_count % 5 == 0:
                            await client.edit_message(ADMIN_USERNAME, status_msg.id, 
                                f"📊 **Hisobot ({phone}):** `{sent_count}` ta xabar.\n"
                                f"📍 Oxirgi ID: `{target_id}`")

                        # Limit tekshirish
                        if sent_count % BATCH_SIZE == 0:
                            waiting_for_admin = True
                            await client.send_message(ADMIN_USERNAME, f"⚠️ **Limit ({BATCH_SIZE}).**\nDavom etish uchun 'Boshla' deb yozing.")
                            while waiting_for_admin: await asyncio.sleep(2)

                        await asyncio.sleep(random.randint(MIN_DELAY, MAX_DELAY))
                    except (PeerFloodError, FloodWaitError):
                        await client.send_message(ADMIN_USERNAME, f"🚨 {phone} spamga tushdi.")
                        break
                    except UserPrivacyRestrictedError: pass
                    except Exception: pass
            await asyncio.sleep(20)

    asyncio.create_task(scraper())
    asyncio.create_task(sender())
    await client.run_until_disconnected()

# ================== ADMIN PANEL (AIOGRAM) ==================
@dp.message(Command("start"), F.from_user.id == ADMIN_ID)
async def cmd_start(message: types.Message):
    kb = [[types.KeyboardButton(text="🚀 Yoqish"), types.KeyboardButton(text="⛔ To'xtatish")],
          [types.KeyboardButton(text="📂 Guruhlar"), types.KeyboardButton(text="📝 Matnlar")],
          [types.KeyboardButton(text="➕ Akkaunt"), types.KeyboardButton(text="📊 Statistika")]]
    await message.answer("🕹 **Boshqaruv markazi**", reply_markup=types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text == "🚀 Yoqish")
async def start_ads(message: types.Message):
    global IS_ADVERTISING
    IS_ADVERTISING = True
    await message.answer("🚀 Jarayon boshlandi!")

@dp.message(F.text == "⛔ To'xtatish")
async def stop_ads(message: types.Message):
    global IS_ADVERTISING
    IS_ADVERTISING = False
    await message.answer("🛑 Jarayon to'xtatildi.")

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT count(*) FROM target_users WHERE status='sent'") as c1:
            sent = (await c1.fetchone())[0]
        async with db.execute("SELECT count(*) FROM target_users WHERE status='pending'") as c2:
            pending = (await c2.fetchone())[0]
    await message.answer(f"📊 **Statistika:**\n✅ Yuborildi: {sent}\n⏳ Navbatda: {pending}")

@dp.message(F.text == "➕ Akkaunt")
async def add_acc_start(message: types.Message, state: FSMContext):
    await message.answer("📞 Raqamni kiriting (+998...):")
    await state.set_state(Form.phone)

@dp.message(Form.phone)
async def add_acc_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    client = TelegramClient(os.path.join(SESSIONS_DIR, phone), API_ID, API_HASH)
    await client.connect()
    try:
        await client.send_code_request(phone)
        await state.update_data(phone=phone, client=client)
        await message.answer("📩 Kodni yuboring:")
        await state.set_state(Form.code)
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
        await state.clear()

@dp.message(Form.code)
async def add_acc_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        await data['client'].sign_in(data['phone'], message.text.strip())
        await finalize_login(message, state, data['phone'])
    except SessionPasswordNeededError:
        await message.answer("🔐 2FA Parolni yuboring:")
        await state.set_state(Form.password)
    except Exception as e: await message.answer(f"Xato: {e}")

@dp.message(Form.password)
async def add_acc_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        await data['client'].sign_in(password=message.text.strip())
        await finalize_login(message, state, data['phone'])
    except Exception as e: await message.answer(f"Xato: {e}")

async def finalize_login(message, state, phone):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO accounts VALUES (?, ?, ?, 'active')", (phone, API_ID, API_HASH))
        await db.commit()
    await message.answer(f"✅ Akkaunt {phone} ulandi!")
    asyncio.create_task(run_userbot(phone, API_ID, API_HASH))
    await state.clear()

@dp.message(F.text == "📂 Guruhlar")
async def list_groups(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT group_id, status FROM groups") as cur: rows = await cur.fetchall()
    builder = InlineKeyboardBuilder()
    for gid, status in rows:
        builder.button(text=f"🗑 {gid}", callback_data=f"del_grp_{gid}")
    builder.button(text="➕ Qo'shish", callback_data="add_group")
    builder.adjust(1)
    await message.answer("📂 Guruhlar ro'yxati:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "add_group")
async def add_group_call(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Guruh ID sini yuboring:")
    await state.set_state(Form.group)

@dp.message(Form.group)
async def save_group(message: types.Message, state: FSMContext):
    try:
        gid = int(message.text)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO groups (group_id) VALUES (?)", (gid,))
            await db.commit()
        await message.answer("✅ Guruh qo'shildi.")
    except: await message.answer("❌ ID xato.")
    await state.clear()

@dp.message(F.text == "📝 Matnlar")
async def list_ads(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, text FROM ads") as cur: rows = await cur.fetchall()
    builder = InlineKeyboardBuilder()
    for aid, txt in rows:
        builder.button(text=f"🗑 {txt[:20]}...", callback_data=f"del_ad_{aid}")
    builder.button(text="➕ Qo'shish", callback_data="add_ad")
    builder.adjust(1)
    await message.answer("📝 Reklama matnlari:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "add_ad")
async def add_ad_call(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Matnni yuboring:")
    await state.set_state(Form.ad)

@dp.message(Form.ad)
async def save_ad(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO ads (text) VALUES (?)", (message.text,))
        await db.commit()
    await message.answer("✅ Matn saqlandi.")
    await state.clear()

@dp.callback_query(F.data.startswith("del_grp_"))
async def del_grp(call: types.CallbackQuery):
    gid = int(call.data.split("_")[2])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM groups WHERE group_id=?", (gid,))
        await db.commit()
    await call.answer("O'chirildi")
    await list_groups(call.message)

@dp.callback_query(F.data.startswith("del_ad_"))
async def del_ad(call: types.CallbackQuery):
    aid = int(call.data.split("_")[2])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM ads WHERE id=?", (aid,))
        await db.commit()
    await call.answer("O'chirildi")
    await list_ads(call.message)

# ================== START ==================
async def main():
    if not os.path.exists(SESSIONS_DIR): os.makedirs(SESSIONS_DIR)
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT phone, api_id, api_hash FROM accounts") as cur:
            accs = await cur.fetchall()
    for acc in accs:
        asyncio.create_task(run_userbot(acc[0], acc[1], acc[2]))
    
    logging.info("🚀 Tizim ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())