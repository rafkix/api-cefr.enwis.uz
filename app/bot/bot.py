import asyncio
import random
import logging
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChatWriteForbiddenError, UserPrivacyRestrictedError
from telethon.tl.functions.contacts import AddContactRequest

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
    
    # 1. Adminga boshlang'ich hisobot xabari
    status_msg = await client.send_message(
        ADMIN_USERNAME, 
        "🚀 **Reklama jarayoni va kontaktga qo'shish boshlandi...**"
    )

    for gid in GROUP_IDS:
        try:
            entity = await client.get_entity(gid)
            group_title = entity.title if hasattr(entity, 'title') else str(gid)
            
            async for user in client.iter_participants(entity, limit=100):
                if user.bot: continue

                try:
                    # --- KONTAKTGA QO'SHISH ---
                    try:
                        await client(AddContactRequest(
                            id=user.id,
                            first_name=user.first_name if user.first_name else "User",
                            last_name="",
                            phone='', 
                            add_phone_privacy_exception=False
                        ))
                        logging.info(f"Kontaktga qo'shildi: {user.id}")
                        await asyncio.sleep(2) # Kontaktga qo'shgach kichik tanaffus
                    except Exception as ce:
                        logging.warning(f"Kontaktga qo'shishda muammo (o'tkazib yuboramiz): {ce}")

                    # --- XABAR YUBORISH ---
                    text = random.choice(POST_VARIANTS)
                    await client.send_message(user.id, text)
                    sent_count += 1
                    
                    user_name = f"@{user.username}" if user.username else f"{user.first_name}"
                    
                    # 2. Hisobotni yangilash
                    report_text = (
                        f"📊 **Jonli Hisobot**\n\n"
                        f"✅ Yuborildi: `{sent_count}`\n"
                        f"❌ Xatoliklar: `{error_count}`\n"
                        f"📍 Guruh: *{group_title}*\n"
                        f"👤 Oxirgi kontakt: {user_name}\n\n"
                        f"🕒 Keyingi foydalanuvchi qidirilmoqda..."
                    )
                    await client.edit_message(ADMIN_USERNAME, status_msg.id, report_text)
                    
                    logging.info(f"Xabar ketdi: {user.id}")
                    
                    # Navbatdagi kutish
                    wait_time = random.randint(MIN_DELAY, MAX_DELAY)
                    await asyncio.sleep(wait_time)

                    # Katta tanaffus (Batch pause)
                    if sent_count % BATCH_SIZE == 0:
                        pause = random.randint(600, 1200)
                        await client.edit_message(
                            ADMIN_USERNAME, 
                            status_msg.id, 
                            report_text + f"\n\n☕ **Batch pauza: {pause//60} daqiqa dam...**"
                        )
                        await asyncio.sleep(pause)

                except UserPrivacyRestrictedError:
                    error_count += 1
                    logging.warning(f"Maxfiylik cheklovi: {user.id}")
                except FloodWaitError as e:
                    logging.error(f"FloodWait: {e.seconds}s")
                    await client.send_message(ADMIN_USERNAME, f"⚠️ FloodWait: {e.seconds}s blok. Kutamiz...")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    error_count += 1
                    logging.error(f"Xatolik: {e}")

        except Exception as e:
            logging.error(f"Guruhni o'qishda xatolik: {e}")

    # 3. Yakunlash
    final_text = f"✅ **Jarayon tugadi!**\n\nJami: {sent_count}\nXatolar: {error_count}"
    await client.edit_message(ADMIN_USERNAME, status_msg.id, final_text)
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(send_posts())