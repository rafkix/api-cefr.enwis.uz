import asyncio
import random
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChatWriteForbiddenError

api_id = 123456
api_hash = "API_HASH"

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

BATCH_SIZE = 10
MIN_DELAY = 60
MAX_DELAY = 180

# ===== LOGGING =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===== MAIN FUNCTION =====
async def send_posts():
    async with TelegramClient("session", api_id, api_hash) as client:

        sent_count = 0
        error_count = 0

        for gid in GROUP_IDS:

            # Stop flag tekshirish
            try:
                with open("stop.txt"):
                    logging.info("Stop flag topildi. To‘xtaymiz.")
                    await client.send_message(
                        ADMIN_USERNAME,
                        "⛔ Jarayon stop.txt orqali to‘xtatildi."
                    )
                    break
            except FileNotFoundError:
                pass

            try:
                text = random.choice(POST_VARIANTS)

                await client.send_message(gid, text)
                sent_count += 1

                logging.info(f"{gid} yuborildi")

                # oddiy delay
                delay = random.randint(MIN_DELAY, MAX_DELAY)
                await asyncio.sleep(delay)

                # batch pause
                if sent_count % BATCH_SIZE == 0:
                    big_pause = random.randint(600, 1800)
                    logging.info(f"{BATCH_SIZE} ta yuborildi. {big_pause}s dam.")
                    await asyncio.sleep(big_pause)

            except FloodWaitError as e:
                logging.warning(f"FloodWait: {e.seconds}s kutamiz")
                await asyncio.sleep(e.seconds)

            except ChatWriteForbiddenError:
                logging.warning(f"Yozishga ruxsat yo‘q: {gid}")
                error_count += 1

            except Exception as e:
                logging.error(f"Xatolik: {e}")
                error_count += 1

        # Jarayon tugaganda admin notify
        await client.send_message(
            ADMIN_USERNAME,
            f"✅ Jarayon tugadi.\n\nYuborildi: {sent_count}\nXatoliklar: {error_count}"
        )


# ===== ENTRY =====
if __name__ == "__main__":
    asyncio.run(send_posts())