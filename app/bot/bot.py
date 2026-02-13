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
    await client.start()
    
    sent_count = 0
    error_count = 0
    
    # 1. Adminga boshlang'ich hisobot xabarini yuboramiz
    status_msg = await client.send_message(
        ADMIN_USERNAME, 
        "🚀 **Reklama jarayoni boshlanmoqda...**"
    )

    for gid in GROUP_IDS:
        try:
            entity = await client.get_entity(gid)
            # Guruh nomini olish
            group_title = entity.title if hasattr(entity, 'title') else str(gid)
            
            async for user in client.iter_participants(entity, limit=100):
                if user.bot: continue

                try:
                    text = random.choice(POST_VARIANTS)
                    await client.send_message(user.id, text)
                    sent_count += 1
                    
                    # Foydalanuvchi nomi (agar bo'lsa)
                    user_name = f"@{user.username}" if user.username else f"{user.first_name}"
                    
                    # 2. Adminga yuborilgan xabarni EDIT qilish
                    report_text = (
                        f"📊 **Jonli Hisobot**\n\n"
                        f"✅ Yuborildi: `{sent_count}`\n"
                        f"❌ Xatoliklar: `{error_count}`\n"
                        f"📍 Guruh: *{group_title}*\n"
                        f"👤 Oxirgi: {user_name} (`{user.id}`)\n\n"
                        f"🕒 Keyingi xabar tayyorlanmoqda..."
                    )
                    await client.edit_message(ADMIN_USERNAME, status_msg.id, report_text)
                    
                    logging.info(f"Yuborildi: {user.id}")
                    
                    # Tasodifiy kutish
                    wait_time = random.randint(MIN_DELAY, MAX_DELAY)
                    await asyncio.sleep(wait_time)

                    # Batch (to'xtalish) vaqti
                    if sent_count % BATCH_SIZE == 0:
                        pause = random.randint(300, 600)
                        logging.info(f"Batch pauza: {pause}s")
                        
                        await client.edit_message(
                            ADMIN_USERNAME, 
                            status_msg.id, 
                            report_text + f"\n\n☕ **Pauza ketmoqda: {pause} soniya...**"
                        )
                        await asyncio.sleep(pause)

                except UserPrivacyRestrictedError:
                    error_count += 1
                    logging.warning("Maxfiylik cheklovi sababli yuborilmadi.")
                except FloodWaitError as e:
                    logging.error(f"FloodWait: {e.seconds}s")
                    await client.send_message(ADMIN_USERNAME, f"⚠️ FloodWait: {e.seconds} soniya blok tushdi. Kutamiz...")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    error_count += 1
                    logging.error(f"Kichik xato: {e}")

        except Exception as e:
            logging.error(f"Guruhda xatolik: {e}")

    # 3. Yakuniy hisobot
    final_text = (
        f"✅ **Jarayon yakunlandi!**\n\n"
        f"Jami muvaffaqiyatli: `{sent_count}`\n"
        f"Jami xatoliklar: `{error_count}`"
    )
    await client.edit_message(ADMIN_USERNAME, status_msg.id, final_text)
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(send_posts())