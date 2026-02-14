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
ADMIN_USERNAME = "bekime06"  # Hisobotlar shu usernamega boradi
GROQ_KEY = "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"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "accounts.db")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")

SYSTEM_PROMPT = """Siz cefr.enwis.uz platformasining aqlli va professional yordamchisisiz. Sizning maqsadingiz foydalanuvchilarga CEFR imtihoniga tayyorlanishda va ingliz tili darajasini oshirishda yaqindan yordam berishdir.

Javob berishda quyidagi tamoyillarga amal qiling:

1. PLATFORMA HAQIDA (Umumiy savollar uchun):
   - Vaqtni tejash: Istalgan joyda, 24/7 online shug'ullanish imkoniyati.
   - Real format: Testlar va interfeys real imtihon atmosferasini to'liq his qildiradi.
   - Bepul resurslar: @enwis_uz Telegram kanalida doimiy bepul testlar va materiallar borligi.
   - Sertifikati borlar uchun: "Sertifikat bor bo'lsa ham, darajani yo'qotmaslik va mahoratni doimiy ravishda sinab turish juda muhim. Platformamiz yangilangan testlar orqali sizga bilimingizni 'fresh' saqlashga yordam beradi".

2. WRITING TAHLILI (Insho yuborilsa):
   - Xatoliklar: Grammatik va punktuatsiya xatolarini aniq ko'rsating.
   - Lug'at (Vocabulary): Lug'at boyligini baholang va takroriy so'zlar o'rniga sinonimlar taklif qiling.
   - Baholash: CEFR mezonlari bo'yicha taxminiy darajani (B1, B2, C1) belgilang.
   - Maslahat: Inshoni yanada yaxshilash uchun kamida 2 ta aniq va foydali maslahat bering.

3. TONA VA USLUB:
   - Doimo muloyim, samimiy va rag'batlantiruvchi tilda gapiring.
   - Javoblar qisqa, tushunarli va faqat o'zbek tilida bo'lishi shart.
   - Har bir foydalanuvchiga potentsial muvaffaqiyat egasi kabi munosabatda bo'ling. 
   
4. Texnik yordam uchun @enwis_support manzili mavjudligini eslatib o'ting."""

active_clients = {}
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_KEY)

class Form(StatesGroup):
    phone = State()
    code = State()
    password = State()
    group = State()
    ad = State()

# ================== BAZA BILAN ISHLASH (WAL REJIMIDA) ==================
async def get_db():
    return aiosqlite.connect(DB_PATH, timeout=30)

async def init_db():
    # await await xatosini oldini olish uchun
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""CREATE TABLE IF NOT EXISTS accounts (
            phone TEXT PRIMARY KEY, ai_status INTEGER DEFAULT 0, ads_status INTEGER DEFAULT 0
        )""")
        # Ustunlarni tekshirish
        try: await db.execute("ALTER TABLE accounts ADD COLUMN ai_status INTEGER DEFAULT 0")
        except: pass
        try: await db.execute("ALTER TABLE accounts ADD COLUMN ads_status INTEGER DEFAULT 0")
        except: pass
        
        await db.execute("CREATE TABLE IF NOT EXISTS groups (group_id TEXT PRIMARY KEY, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS target_users (user_id INTEGER PRIMARY KEY, group_id TEXT, status TEXT DEFAULT 'pending')")
        await db.commit()

# ================== USERBOT ASOSIY MANTIQI ==================
async def run_userbot(phone):
    client = TelegramClient(os.path.join(SESSIONS_DIR, phone), API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized(): return
        active_clients[phone] = client
        logging.info(f"Userbot yoqildi: {phone}")
    except Exception as e:
        logging.error(f"Xato {phone}: {e}"); return

    # 1. AI JAVOB BERISH
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def ai_handler(event):
        async with await get_db() as db:
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
        except: pass

    # 2. REKLAMA TARQATISH (ADS)
    async def ads_sender_loop():
        sent_local = 0
        while True:
            try:
                async with await get_db() as db:
                    async with db.execute("SELECT ads_status FROM accounts WHERE phone=?", (phone,)) as cur:
                        row = await cur.fetchone()
                        if not row or row[0] == 0: 
                            await asyncio.sleep(20); continue

                    async with db.execute("SELECT user_id FROM target_users WHERE status='pending' LIMIT 1") as cur:
                        target = await cur.fetchone()
                    async with db.execute("SELECT text FROM ads ORDER BY RANDOM() LIMIT 1") as cur_ad:
                        ad = await cur_ad.fetchone()

                if target and ad:
                    u_id = target[0]
                    # Kontaktga qo'shish (Spam filtri uchun)
                    try:
                        await client(AddContactRequest(id=u_id, first_name="User", last_name="", phone="", add_phone_privacy_exception=False))
                        await asyncio.sleep(2)
                    except: pass
                    
                    await client.send_message(u_id, ad[0])
                    
                    async with await get_db() as db:
                        await db.execute("UPDATE target_users SET status='sent' WHERE user_id=?", (u_id,))
                        await db.commit()
                    
                    sent_local += 1
                    # HISOBOTNI ADMIN USERNAME'GA YUBORISH
                    report = f"🚀 **ADS REPORT ({phone})**\n✅ Yuborildi: {sent_local}\n👤 User ID: {u_id}"
                    await client.send_message(ADMIN_USERNAME, report)
                    
                    await asyncio.sleep(random.randint(120, 300)) # Spamdan himoya
                else:
                    await asyncio.sleep(60)
            except (PeerFloodError, FloodWaitError):
                await client.send_message(ADMIN_USERNAME, f"⚠️ {phone} SPAMGA TUSHDI! Ads to'xtatildi.")
                async with await get_db() as db:
                    await db.execute("UPDATE accounts SET ads_status=0 WHERE phone=?", (phone,))
                    await db.commit()
                break
            except Exception:
                await asyncio.sleep(30)

    # 3. GURUHNI SKANER QILISH
    async def scraper_loop():
        while True:
            async with await get_db() as db:
                async with db.execute("SELECT group_id FROM groups WHERE status='pending' LIMIT 1") as cur:
                    row = await cur.fetchone()
            if row:
                grp = row[0]
                try:
                    count = 0
                    async for user in client.iter_participants(grp, limit=500):
                        if not user.bot and not user.deleted:
                            async with await get_db() as db:
                                await db.execute("INSERT OR IGNORE INTO target_users (user_id, group_id) VALUES (?, ?)", (user.id, grp))
                                await db.commit()
                            count += 1
                    async with await get_db() as db:
                        await db.execute("UPDATE groups SET status='done' WHERE group_id=?", (grp,))
                        await db.commit()
                    await client.send_message(ADMIN_USERNAME, f"✅ Skaner tugadi: {grp}\n👤 {count} ta foydalanuvchi yig'ildi.")
                except: pass
            await asyncio.sleep(120)

    asyncio.create_task(ads_sender_loop())
    asyncio.create_task(scraper_loop())
    await client.run_until_disconnected()

# ================== ADMIN PANEL (AIOGRAM) ==================
@dp.message(Command("start"), F.from_user.id == ADMIN_ID)
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="📱 Akkauntlarni boshqarish"))
    kb.row(types.KeyboardButton(text="➕ Akkaunt qo'shish"), types.KeyboardButton(text="📊 Statistika"))
    kb.row(types.KeyboardButton(text="📂 Guruhlar"), types.KeyboardButton(text="📝 Matnlar"))
    await message.answer("🕹 **Boshqaruv markazi**", reply_markup=kb.as_markup(resize_keyboard=True))

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    async with await get_db() as db:
        async with db.execute("SELECT count(*) FROM target_users WHERE status='sent'") as c1: s = (await c1.fetchone())[0]
        async with db.execute("SELECT count(*) FROM target_users WHERE status='pending'") as c2: p = (await c2.fetchone())[0]
        async with db.execute("SELECT count(*) FROM accounts") as c3: a = (await c3.fetchone())[0]
    await message.answer(f"📊 **Statistika:**\n\n✅ Reklama yuborildi: {s}\n⏳ Navbatda: {p}\n📱 Akkauntlar: {a}")

@dp.message(F.text == "📱 Akkauntlarni boshqarish")
async def list_accs(message: types.Message):
    async with await get_db() as db:
        async with db.execute("SELECT phone, ai_status, ads_status FROM accounts") as cur: rows = await cur.fetchall()
    if not rows: return await message.answer("Akkauntlar yo'q.")
    for phone, ai, ads in rows:
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
    async with await get_db() as db:
        await db.execute(f"UPDATE accounts SET {col} = 1 - {col} WHERE phone=?", (phone,))
        await db.commit()
    await call.message.delete()
    await list_accs(call.message)

@dp.callback_query(F.data.startswith("rem_acc_"))
async def remover(call: types.CallbackQuery):
    phone = call.data.split("_")[2]
    async with await get_db() as db:
        await db.execute("DELETE FROM accounts WHERE phone=?", (phone,))
        await db.commit()
    if phone in active_clients: await active_clients[phone].disconnect()
    await call.answer("O'chirildi"); await call.message.delete()

# --- QO'SHISH FUNKSIYALARI ---
@dp.message(F.text == "➕ Akkaunt qo'shish")
async def add_a_start(message: types.Message, state: FSMContext):
    await message.answer("Raqamni kiriting (+998...):"); await state.set_state(Form.phone)

@dp.message(Form.phone)
async def add_a_ph(message: types.Message, state: FSMContext):
    ph = message.text.replace(" ", "")
    cl = TelegramClient(os.path.join(SESSIONS_DIR, ph), API_ID, API_HASH)
    await cl.connect()
    try:
        s = await cl.send_code_request(ph)
        await state.update_data(phone=ph, client=cl, hash=s.phone_code_hash)
        await message.answer("Kodni yuboring:"); await state.set_state(Form.code)
    except Exception as e: await message.answer(f"Xato: {e}")

@dp.message(Form.code)
async def add_a_cd(message: types.Message, state: FSMContext):
    d = await state.get_data()
    try:
        await d['client'].sign_in(d['phone'], message.text, phone_code_hash=d['hash'])
        async with await get_db() as db:
            await db.execute("INSERT OR REPLACE INTO accounts (phone, ai_status, ads_status) VALUES (?, 0, 0)", (d['phone'], 0, 0))
            await db.commit()
        asyncio.create_task(run_userbot(d['phone']))
        await message.answer(f"✅ {d['phone']} ulandi!"); await state.clear()
    except SessionPasswordNeededError:
        await message.answer("2FA parolni kiriting:"); await state.set_state(Form.password)
    except Exception as e: await message.answer(f"Xato: {e}")

@dp.message(Form.password)
async def add_a_ps(message: types.Message, state: FSMContext):
    d = await state.get_data()
    await d['client'].sign_in(password=message.text)
    async with await get_db() as db:
        await db.execute("INSERT OR REPLACE INTO accounts (phone, ai_status, ads_status) VALUES (?, 0, 0)", (d['phone'], 0, 0))
        await db.commit()
    asyncio.create_task(run_userbot(d['phone']))
    await message.answer("✅ Ulandi!"); await state.clear()

@dp.message(F.text == "📂 Guruhlar")
async def m_groups(message: types.Message):
    ib = InlineKeyboardBuilder().button(text="➕ Guruh qo'shish", callback_data="add_grp")
    await message.answer("Skaner guruhlari:", reply_markup=ib.as_markup())

@dp.callback_query(F.data == "add_grp")
async def add_g_call(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Guruh username (masalan: @groupname):"); await state.set_state(Form.group)

@dp.message(Form.group)
async def save_g(message: types.Message, state: FSMContext):
    async with await get_db() as db:
        await db.execute("INSERT OR IGNORE INTO groups (group_id) VALUES (?)", (message.text,))
        await db.commit()
    await message.answer("✅ Guruh skanerga qo'shildi."); await state.clear()

@dp.message(F.text == "📝 Matnlar")
async def m_ads(message: types.Message):
    ib = InlineKeyboardBuilder().button(text="➕ Yangi matn", callback_data="add_ad")
    await message.answer("Reklama matnlari:", reply_markup=ib.as_markup())

@dp.callback_query(F.data == "add_ad")
async def add_a_call(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Reklama matnini yuboring:"); await state.set_state(Form.ad)

@dp.message(Form.ad)
async def save_a(message: types.Message, state: FSMContext):
    async with await get_db() as db:
        await db.execute("INSERT INTO ads (text) VALUES (?)", (message.text,))
        await db.commit()
    await message.answer("✅ Matn saqlandi."); await state.clear()

# ================== START ==================
async def main():
    if not os.path.exists(SESSIONS_DIR): os.makedirs(SESSIONS_DIR)
    await init_db()
    async with await get_db() as db:
        async with db.execute("SELECT phone FROM accounts") as cur: accs = await cur.fetchall()
    for a in accs: asyncio.create_task(run_userbot(a[0]))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())