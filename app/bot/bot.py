import asyncio
import random
import logging, os
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, ChatWriteForbiddenError, UserPrivacyRestrictedError
from telethon.tl.functions.contacts import AddContactRequest
from openai import AsyncOpenAI

api_id = 32844127
api_hash = "680be0244466d6be0195e23c31a9f0f2"
aclient = AsyncOpenAI(api_key="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")

# int bo‘lishi shart
GROUP_IDS = [
    -1002081866272,
    -1001904343166,
    -1002040221500,
    -1002228254267,
    -1001645803241,
    -1001716615530
]

POST_VARIANTS = [
    """😊🇺🇸 CEFR imtihoniga tayyorgarlik — endi yanada oson va qulay!

🌐 cefr.enwis.uz platformasining birinchi bosqichi ishga tushdi!
Endi siz istalgan joyda va istalgan vaqtda bilimingizni real imtihon formatida sinab ko‘rishingiz mumkin.

🔹 Hozirda faol bo‘limlar:
📖 Reading — Matnlarni tahlil qilish va test savollariga javob berish.
🎧 Listening — Audio topshiriqlar orqali tushunish darajangizni aniqlash.

🚀 Tez orada qolgan bo‘limlar ham qo‘shiladi!

📲 Shuningdek, maxsus Telegram kanalimizda:
— Foydali maslahatlar
— Bepul testlar
— Imtihon yangiliklari
— Tayyorlanish strategiyalari muntazam ulashib boriladi.

Imkoniyatni qo‘ldan boy bermang!

👉 Platforma: https://cefr.enwis.uz

👉 Telegram kanal: @enwis_uz 

Bilim olishdan to‘xtamang — natija albatta keladi! 💪🔥""",

    """🇺🇸 CEFR imtihoniga puxta tayyorgarlik ko‘rmoqchimisiz?

Endi real imtihon formatidagi topshiriqlar bilan o‘zingizni sinab ko‘rishingiz mumkin!

🌐 cefr.enwis.uz platformasi ishga tushdi.

🔎 Mavjud bo‘limlar:
📖 Reading — Matnlarni chuqur tahlil qilish
🎧 Listening — Audio orqali tushunish darajasini aniqlash

✅ Qulay interfeys
✅ Real test format
✅ Mustaqil mashq qilish imkoniyati

🚀 Tez orada Writing va Speaking ham qo‘shiladi!

👉 Platforma: https://cefr.enwis.uz

👉 Telegram kanal: @enwis_uz

Bugundan tayyorgarlikni boshlang — natijangiz sizni hayratlantiradi!""",

    """CEFR imtihoniga tayyorlanish qiyin tuyulyaptimi? 🤔

Ko‘pchilik:
❌ Qayerdan boshlashni bilmaydi
❌ Real formatni ko‘rmagan bo‘ladi
❌ Yetarli amaliyot qilmaydi

Shu sababli biz yaratdik —
🇺🇸 cefr.enwis.uz

Bu yerda siz:
📖 Reading testlarini ishlaysiz
🎧 Listening mashqlarini bajarasiz
📊 Darajangizni tekshirasiz

Hammasi online va qulay!

👉 Hozir sinab ko‘ring: https://cefr.enwis.uz

👉 Kanal: @enwis_uz

CEFR natijangizni bugundan oshirishni boshlang 🚀"""

"""
🇺🇸 CEFR imtihoniga tayyormisiz?

Endi real formatdagi testlar bilan o‘zingizni sinab ko‘ring!

📖 Reading
🎧 Listening
🚀 Yangi bo‘limlar tez orada

👉 https://cefr.enwis.uz

👉 @enwis_uz

Imtihonga tayyorgarlikni bugundan boshlang 💪🔥
"""
]

SYSTEM_PROMPT = """
Siz cefr.enwis.uz platformasining professional yordamchisisiz. 
Platforma vazifasi: CEFR imtihoniga (Reading, Listening) real formatda tayyorlash.
Foydalanuvchi savol bersa (masalan: "Nima foydasi bor?", "Kim bu?", "Menga kerakmi?"), quyidagilarni ta'kidlang:
1. Vaqtni tejash: Istalgan joyda online shug'ullanish mumkin.
2. Real format: Imtihon atmosferasini his qilish.
3. Bepul testlar: @enwis_uz kanalida foydali materiallar borligi.
Javobingiz qisqa, samimiy va o'zbek tilida bo'lsin.
"""

ADMIN_USERNAME = "bekime06"
BATCH_SIZE = 50
MIN_DELAY = 30
MAX_DELAY = 50
SENT_USERS_FILE = "sent_users.txt"  # Yuborilganlar ro'yxati saqlanadigan fayl

# --- GLOBAL HOLATLAR ---
is_paused = False
waiting_for_admin = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
client = TelegramClient("my_account_session", api_id, api_hash)

# --- FUNKSIYALAR: FOYDALANUVCHILARNI BOSHQARISH ---
def get_sent_users():
    """Fayldan yuborilgan user IDlarini o'qiydi"""
    if not os.path.exists(SENT_USERS_FILE):
        return set()
    with open(SENT_USERS_FILE, "r") as f:
        return set(line.strip() for line in f)

def save_sent_user(user_id):
    """Yangi yuborilgan user IDsini faylga qo'shadi"""
    with open(SENT_USERS_FILE, "a") as f:
        f.write(f"{user_id}\n")
        
# ================== AI JAVOB BERISH QISMI ==================
@client.on(events.NewMessage(incoming=True))
async def ai_responder(event):
    if event.is_private:
        # Foydalanuvchi ma'lumotlarini olish
        sender = await event.get_sender()
        
        # Agar sender topilmasa yoki u bot bo'lsa, javob bermaymiz
        if not sender or sender.bot:
            return

        # Agar admin o'zi yozayotgan bo'lsa, AI aralashmaydi
        me = await client.get_me()
        if sender.id == me.id:
            return

        # Admin buyruqlarini tekshirish
        if event.text.lower() in ["/start", "/stop"]:
            return

        try:
            async with client.action(event.chat_id, 'typing'):
                response = await aclient.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "system", "content": SYSTEM_PROMPT},
                              {"role": "user", "content": event.text}],
                    max_tokens=250
                )
                await asyncio.sleep(2) # Tabiiy ko'rinish uchun
                await event.reply(response.choices[0].message.content)
        except Exception as e:
            logging.error(f"AI xatosi: {e}")
        

# --- ADMIN BUYRUQLARINI QABUL QILISH ---
@client.on(events.NewMessage(chats=ADMIN_USERNAME))
async def admin_handler(event):
    global is_paused, waiting_for_admin
    msg = event.text.lower()
    
    if "/stop" in msg:
        is_paused = True
        waiting_for_admin = False
        await event.reply("⛔ **Jarayon to'xtatildi va 5 daqiqa kutish rejimiga o'tildi.**")
    
    elif "/start" in msg:
        is_paused = False
        waiting_for_admin = False
        await event.reply("🚀 **Jarayon qayta boshlandi!**")

# --- ASOSIY JARAYON ---
async def send_posts():
    global is_paused, waiting_for_admin
    await client.start()
    
    sent_count = 0
    error_count = 0
    sent_users = get_sent_users() # Eski yuborilganlarni yuklash
    
    status_msg = await client.send_message(ADMIN_USERNAME, "🚀 **Userbot ishga tushdi.**")

    for gid in GROUP_IDS:
        try:
            entity = await client.get_entity(gid)
            group_title = entity.title if hasattr(entity, 'title') else str(gid)
            
            async for user in client.iter_participants(entity, limit=200):
                # 1. Tekshirish: Userbot yoki oldin yuborilganmi?
                if user.bot or str(user.id) in sent_users:
                    continue

                # 2. Admin to'xtatgan bo'lsa 5 daqiqa kutish
                if is_paused:
                    logging.info("Pauza rejimi: 5 daqiqa...")
                    await asyncio.sleep(200) 
                    is_paused = False

                try:
                    # Kontaktga qo'shish
                    try:
                        await client(AddContactRequest(
                            id=user.id, 
                            first_name=user.first_name or "User", 
                            last_name="", phone='', 
                            add_phone_privacy_exception=False
                        ))
                        await asyncio.sleep(3)
                    except: pass

                    # Xabar yuborish
                    await client.send_message(user.id, random.choice(POST_VARIANTS))
                    
                    # Saqlash
                    sent_count += 1
                    sent_users.add(str(user.id))
                    save_sent_user(user.id)
                    
                    user_name = f"@{user.username}" if user.username else f"{user.first_name}"
                    await client.edit_message(ADMIN_USERNAME, status_msg.id, 
                        f"📊 **Hisobot:** `{sent_count}` ta yangi xabar.\n"
                        f"📍 Guruh: {group_title}\n"
                        f"👤 Oxirgi: {user_name}\n"
                        f"📚 Jami bazada: {len(sent_users)} ta user.")

                    # --- LIMIT VA ADMIN MULOQOTI ---
                    if sent_count % BATCH_SIZE == 0:
                        waiting_for_admin = True
                        await client.send_message(ADMIN_USERNAME, 
                            f"⚠️ **Limitga yetdi ({sent_count}).**\n\nNima qilamiz?\n"
                            f"• **'To'xtat'** - 5 daqiqa kutish.\n"
                            f"• **'Boshla'** - Davom etish.")
                        
                        wait_timer = 0
                        while waiting_for_admin and wait_timer < 600:
                            await asyncio.sleep(1)
                            wait_timer += 1

                    await asyncio.sleep(random.randint(MIN_DELAY, MAX_DELAY))

                except UserPrivacyRestrictedError:
                    continue
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception:
                    error_count += 1

        except Exception as e:
            logging.error(f"Xato: {e}")

    await client.send_message(ADMIN_USERNAME, "✅ Barcha guruhlar ko'rib chiqildi.")

if __name__ == "__main__":
    client.loop.run_until_complete(send_posts())