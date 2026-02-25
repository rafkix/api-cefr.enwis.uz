# main.py
import asyncio
from app.bot.userbot import bot1
# from app.bot.userbot import bot2
# from app.bot.userbot import bot3 # Botlar soniga qarab davom etaveradi

async def main():
    print("🚀 Barcha botlar ishga tushirilmoqda...")
    
    # Har bir botning start_bot funksiyasini ro'yxatga olamiz
    tasks = [
        bot1.start_bot(),
        # bot2.start_bot(),
        # bot3.start_bot()
    ]
    
    # Hammasini parallel ishga tushiramiz
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Barcha botlar to'xtatildi.")