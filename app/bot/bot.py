import asyncio
import random
import logging
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChatWriteForbiddenError

api_id = 32844127
api_hash = "680be0244466d6be0195e23c31a9f0f2"

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

ADMIN_USERNAME = "bekime06"
BATCH_SIZE = 5 # Xavfsizlik uchun kamaytirdik
MIN_DELAY = 30
MAX_DELAY = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

async def send_posts():
    client = TelegramClient("my_account_session", api_id, api_hash)
    await client.start() # Bu yerda kod so'rashi mumkin
    
    sent_count = 0
    error_count = 0

    for gid in GROUP_IDS:
        try:
            entity = await client.get_entity(gid)
            # Faqat oxirgi faol 50 ta odamni olish (Spamdan qochish uchun)
            async for user in client.iter_participants(entity, limit=100):
                if user.bot: continue # Botlarga yubormaymiz

                try:
                    text = random.choice(POST_VARIANTS)
                    await client.send_message(user.id, text)
                    sent_count += 1
                    logging.info(f"Yuborildi: {user.id}")
                    
                    # Har bir xabardan keyin kutish
                    await asyncio.sleep(random.randint(MIN_DELAY, MAX_DELAY))

                    if sent_count % BATCH_SIZE == 0:
                        pause = random.randint(300, 600)
                        logging.info(f"Batch tugadi. {pause} soniya dam...")
                        await client.send_message(ADMIN_USERNAME, f"Batch tugadi. {pause} soniya dam...")
                        await asyncio.sleep(pause)

                except UserPrivacyRestrictedError:
                    logging.warning("Foydalanuvchi shaxsiy xabarlarni yopib qo'ygan.")
                except FloodWaitError as e:
                    logging.error(f"FloodWait: {e.seconds} soniya kutish kerak.")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logging.error(f"Kichik xato: {e}")

        except Exception as e:
            logging.error(f"Guruhda xatolik: {e}")

    await client.send_message(ADMIN_USERNAME, f"Tugadi. Yuborildi: {sent_count}")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(send_posts())