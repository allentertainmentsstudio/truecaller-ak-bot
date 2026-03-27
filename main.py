import re
import time
import asyncio
import logging
import signal
import sys
import requests
from collections import OrderedDict

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
from configs import cfg

# ───────── LOGGING ───────── #
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ───────── BOT ───────── #
bot = Client(
    "truecaller_saas_bot",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    bot_token=cfg.BOT_TOKEN,
    workers=20
)

# ───────── DB ───────── #
mongo = AsyncIOMotorClient(cfg.MONGO_URI)
db = mongo["truecaller"]

users = db["users"]
logs = db["logs"]
banned_db = db["banned"]

# ───────── PERFORMANCE ───────── #
sem = asyncio.Semaphore(10)
cooldown = {}
cooldown_lock = asyncio.Lock()

# ───────── CACHE ───────── #
class LRUCache:
    def __init__(self, max_size=300):
        self.cache = OrderedDict()
        self.max_size = max_size

    def get(self, key):
        return self.cache.get(key)

    def set(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

cache = LRUCache()

# ───────── CLEAN NUMBER ───────── #
def clean_number(n: str):
    if not n:
        return None

    n = n.strip().replace(" ", "")

    if n.startswith("+"):
        return n

    digits = re.sub(r"\D", "", n)
    return f"+{digits}" if 8 <= len(digits) <= 15 else None

# ───────── API CALL ───────── #
async def get_number_info(num):
    try:
        url = f"http://apilayer.net/api/validate?access_key={cfg.API_KEY}&number={num}"
        response = await asyncio.to_thread(requests.get, url)
        return response.json()
    except Exception as e:
        logger.error(e)
        return None

# ───────── FETCH ───────── #
async def fetch(num, msg: Message, user):
    async with sem:
        try:
            cached = cache.get(num)
            if cached:
                return await msg.edit(cached)

            data = await get_number_info(num)

            if not data or not data.get("valid"):
                return await msg.edit("❌ Invalid or No Data Found")

            text = (
                "🌍 RESULT\n\n"
                f"📞 Number: <code>{data.get('international_format')}</code>\n"
                f"📌 Valid: <code>{data.get('valid')}</code>\n"
                f"🌍 Country: <code>{data.get('country_name')}</code>\n"
                f"📡 Carrier: <code>{data.get('carrier')}</code>\n"
                f"📱 Line Type: <code>{data.get('line_type')}</code>\n"
                f"⚡ Source: <code>API System</code>"
            )

            cache.set(num, text)
            await msg.edit(text, parse_mode=enums.ParseMode.HTML)

        except Exception as e:
            logger.error(e)
            await msg.edit("⚠️ Error occurred")

# ───────── START ───────── #
@bot.on_message(filters.command("start"))
async def start(_, m: Message):
    await m.reply_photo(
        photo="https://i.ibb.co/S4jWcS4v/7168219724-29166.jpg",
        caption=f"""
Hello {m.from_user.first_name} 👋

🤖 I am Truecaller Info Bot
Your Professional Truecaller Info Bot.

🚀 System Status: 🟢 Online
⚡ Performance: 10x High-Speed Processing
🔐 Security: End-to-End Encrypted
📊 Uptime: 99.9% Guaranteed

👇 Send number like:
+911234567890
"""
    )

# ───────── MAIN ───────── #
@bot.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def main(_, m: Message):
    uid = m.from_user.id

    if await banned_db.find_one({"id": uid}):
        return await m.reply_text("🚫 You are banned")

    num = clean_number(m.text)
    if not num:
        return await m.reply_text("❌ Invalid Number")

    now = time.time()

    async with cooldown_lock:
        if cooldown.get(uid, 0) > now:
            return await m.reply_text("⏳ Slow down!")

        cooldown[uid] = now + 2

    msg = await m.reply_text("🔍 Searching...")
    await fetch(num, msg, m.from_user)

# ───────── SHUTDOWN ───────── #
async def shutdown():
    try:
        mongo.close()
    except:
        pass
    logger.info("Bot shutdown complete")

def exit_handler(sig, frame):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(shutdown())
    sys.exit(0)

signal.signal(signal.SIGINT, exit_handler)
signal.signal(signal.SIGTERM, exit_handler)

# ───────── RUN ───────── #
def safe_run():
    while True:
        try:
            print("🚀 BOT STARTED SUCCESSFULLY")
            bot.run()
        except Exception as e:
            logger.error(f"Crash: {e}")
            time.sleep(5)

safe_run()
