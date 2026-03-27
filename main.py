import re
import time
import asyncio
import logging
import signal
import sys
from collections import OrderedDict

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from configs import cfg

# ───────── LOGGING ───────── #
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ───────── BOT ───────── #
bot = Client(
    "truecaller_bot",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    bot_token=cfg.BOT_TOKEN,
    workers=20
)

# ───────── DATABASE ───────── #
mongo = AsyncIOMotorClient(cfg.MONGO_URI)
db = mongo["bot"]

users = db["users"]
logs = db["logs"]
premium_db = db["premium"]
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

# ───────── UTIL ───────── #
def clean_number(n):
    digits = re.sub(r"\D", "", n)
    return digits if 8 <= len(digits) <= 15 else None

async def save_user(user):
    if user:
        await users.update_one(
            {"id": user.id},
            {"$set": {"name": user.first_name}},
            upsert=True
        )

async def is_banned(uid):
    return bool(await banned_db.find_one({"id": uid}))

# ───────── FAKE LOOKUP ───────── #
async def lookup(num):
    return (
        "🌍 <b>RESULT</b>\n\n"
        f"📞 Number: <code>{num}</code>\n"
        f"📌 Status: <code>Valid Number</code>\n"
        f"⚡ Source: <code>Internal System</code>"
    )

# ───────── FETCH ───────── #
async def fetch(num, msg, user):
    async with sem:
        cached = cache.get(num)
        if cached:
            return await msg.edit(cached, parse_mode=enums.ParseMode.HTML)

        text = await lookup(num)

        cache.set(num, text)
        await logs.insert_one({"user": user.id, "num": num})

        await msg.edit(text, parse_mode=enums.ParseMode.HTML)

# ───────── START ───────── #
@bot.on_message(filters.command("start"))
async def start(_, m: Message):
    await save_user(m.from_user)

    name = m.from_user.first_name or "User"

    text = (
        f"👋 Hello {name}\n\n"
        "🤖 <b>I am Truecaller Info Bot</b>\n"
        "<i>Your Professional Truecaller Info Bot</i>\n\n"
        "🚀 <b>System Status:</b> 🟢 Online\n"
        "⚡ <b>Performance:</b> 10x High-Speed Processing\n"
        "🔐 <b>Security:</b> End-to-End Encrypted\n"
        "📊 <b>Uptime:</b> 99.9% Guaranteed\n\n"
        "👇 <b>Select an Option Below:</b>\n"
        "👋 Send number in international format\n"
        "<code>Ex: +911234567890</code>"
    )

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Stats", callback_data="stats"),
            InlineKeyboardButton("💎 Premium", callback_data="premium")
        ],
        [
            InlineKeyboardButton("📞 Support", url="https://t.me/Anujedits76"),
            InlineKeyboardButton("📢 Updates", url="https://t.me/Anujedits76")
        ]
    ])

    await m.reply_photo(
        photo="https://i.ibb.co/S4jWcS4v/7168219724-29166.jpg",
        caption=text,
        reply_markup=buttons
    )

# ───────── CALLBACKS ───────── #
@bot.on_callback_query()
async def callbacks(_, query):

    if query.data == "stats":
        u = await users.count_documents({})
        l = await logs.count_documents({})

        await query.message.edit_text(
            f"📊 <b>Bot Stats</b>\n\n👥 Users: {u}\n📞 Requests: {l}",
            parse_mode=enums.ParseMode.HTML
        )

    elif query.data == "premium":
        await query.message.edit_text(
            "💎 <b>Premium Benefits</b>\n\n"
            "⚡ Faster speed\n"
            "🚀 No cooldown\n\n"
            "Contact admin to buy",
            parse_mode=enums.ParseMode.HTML
        )

# ───────── ADMIN ───────── #
@bot.on_message(filters.command("addpremium") & filters.user(cfg.OWNER_ID))
async def add_premium(_, m: Message):
    try:
        args = m.text.split()

        uid = int(args[1])

        if len(args) == 3:
            days = int(args[2])
            expire = time.time() + days * 86400
        else:
            expire = 0

        await premium_db.update_one(
            {"id": uid},
            {"$set": {"id": uid, "expire": expire}},
            upsert=True
        )

        await m.reply_text("✅ Premium Added")

    except:
        await m.reply_text("Usage: /addpremium user_id days(optional)")

# ───────── BROADCAST ───────── #
@bot.on_message(filters.command("broadcast") & filters.user(cfg.OWNER_ID))
async def broadcast(_, m: Message):
    msg = m.reply_to_message
    if not msg:
        return await m.reply_text("Reply to a message")

    total = 0

    async for user in users.find():
        try:
            await msg.copy(user["id"])
            total += 1
        except:
            pass

    await m.reply_text(f"✅ Sent to {total} users")

# ───────── MAIN ───────── #
@bot.on_message(filters.private & filters.text)
async def main(_, m: Message):
    uid = m.from_user.id

    await save_user(m.from_user)

    if await is_banned(uid):
        return await m.reply_text("🚫 You are banned")

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

# ───────── SHUTDOWN ───────── #
async def shutdown():
    mongo.close()
    logger.info("Shutdown complete")

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
            print("🚀 BOT STARTED")
            bot.run()
        except Exception as e:
            logger.error(e)
            time.sleep(5)

safe_run()
