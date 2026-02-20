from telegram import Bot
import asyncio

BOT_TOKEN = open('.env').read().split('=')[1].strip()
CHAT_ID = -5162511716

async def test():
    bot = Bot(BOT_TOKEN)
    count = await bot.get_chat_member_count(CHAT_ID)
    print(f"Chat member count: {count}")

asyncio.run(test())
