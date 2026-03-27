import re
import time
import asyncio
import logging
import signal
import sys
from collections import OrderedDict

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
from configs import cfg

# LOGGING
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# BOT
bot = Client(
    "safe_bot",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    bot_token=cfg.BOT_TOKEN,
    workers=20
)

# DB
mongo = AsyncIOMotorClient(cfg.MONGO_URI)
db = mongo["bot"]

users = db["users"]
logs = db["logs"]
premium_db = db["premium"]
banned_db = db["banned"]

# PERFORMANCE
sem = asyncio.Semaphore(10)
cooldown = {}
cooldown_lock = asyncio.Lock()

# CACHE
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

# CLEAN NUMBER
def clean_number(n):
    digits = re.sub(r"\D", "", n)
    return digits if 8 <= len(digits) <= 15 else None

# SAVE USER
async def save_user(user):
    if user:
        await users.update_one(
            {"id": user.id},
            {"$set": {"name": user.first_name}},
            upsert=True
        )

# CHECKS
async def is_banned(uid):
    return bool(await banned_db.find_one({"id": uid}))

async def is_premium(uid):
    return bool(await premium_db.find_one({"id": uid}))

# FAKE LOOKUP (NO API)
async def fake_lookup(num):
    return (
        "🌍 RESULT\n\n"
        f"📞 Number: <code>{num}</code>\n"
        f"📌 Status: <code>Valid Number</code>\n"
        f"⚡ Source: <code>Internal System</code>"
    )

# FETCH
async def fetch(num, msg, user):
    async with sem:
        cached = cache.get(num)
        if cached:
            return await msg.edit(cached)

        text = await fake_lookup(num)

        cache.set(num, text)
        await logs.insert_one({"user": user.id, "num": num})

        await msg.edit(text, parse_mode=enums.ParseMode.HTML)

# START
@bot.on_message(filters.command("start"))
async def start(_, m):
    await save_user(m.from_user)

    await m.reply_text(
        "🚀 Bot Ready\n\n📞 Send any number",
        reply_markup=None
    )

# ADD PREMIUM
@bot.on_message(filters.command("addpremium") & filters.user(cfg.OWNER_ID))
async def add_premium(_, m):
    try:
        args = m.text.split()

        uid = int(args[1])

        if len(args) == 3:
            days = int(args[2])
            expire = time.time() + days * 86400
        else:
            expire = 0  # permanent

        await premium_db.update_one(
            {"id": uid},
            {"$set": {"id": uid, "expire": expire}},
            upsert=True
        )

        await m.reply_text("✅ Premium Added")

    except:
        await m.reply_text("Usage: /addpremium user_id days(optional)")

# BROADCAST
@bot.on_message(filters.command("broadcast") & filters.user(cfg.OWNER_ID))
async def broadcast(_, m):
    msg = m.reply_to_message
    if not msg:
        return await m.reply_text("Reply to message")

    total = 0

    async for user in users.find():
        try:
            await msg.copy(user["id"])
            total += 1
        except:
            pass

    await m.reply_text(f"✅ Sent to {total} users")

# STATS
@bot.on_message(filters.command("stats") & filters.user(cfg.OWNER_ID))
async def stats(_, m):
    u = await users.count_documents({})
    l = await logs.count_documents({})
    await m.reply_text(f"👥 Users: {u}\n📊 Logs: {l}")

# MAIN
@bot.on_message(filters.private & filters.text)
async def main(_, m):
    uid = m.from_user.id

    await save_user(m.from_user)

    if await is_banned(uid):
        return await m.reply_text("🚫 Banned")

    num = clean_number(m.text)
    if not num:
        return await m.reply_text("❌ Invalid Number")

    now = time.time()

    async with cooldown_lock:
        if cooldown.get(uid, 0) > now:
            return await m.reply_text("⏳ Slow down")

        cooldown[uid] = now + 2

    msg = await m.reply_text("🔍 Searching...")
    await fetch(num, msg, m.from_user)

# RUN
def safe_run():
    while True:
        try:
            print("🚀 BOT STARTED")
            bot.run()
        except Exception as e:
            logger.error(e)
            time.sleep(5)

safe_run()
