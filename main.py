import re
import time
import asyncio
import logging
import requests

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from config import cfg

# LOGGING
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ENV CHECK
if not cfg.BOT_TOKEN or not cfg.API_ID:
    raise ValueError("❌ Missing BOT_TOKEN / API_ID")

if not cfg.API_KEY:
    raise ValueError("❌ Missing API_KEY")

# BOT
bot = Client(
    "truecaller_bot",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    bot_token=cfg.BOT_TOKEN,
    workers=20
)

# DATABASE SAFE
try:
    mongo = AsyncIOMotorClient(cfg.MONGO_URI, serverSelectionTimeoutMS=5000)
    db = mongo["truecaller"]

    users = db["users"]
    banned_db = db["banned"]

except Exception as e:
    logger.error(f"Mongo Error: {e}")
    users = None
    banned_db = None

cooldown = {}

# CLEAN NUMBER
def clean_number(n: str):
    if not n:
        return None

    n = n.strip().replace(" ", "")
    digits = re.sub(r"\D", "", n)

    if len(digits) < 8:
        return None

    if not digits.startswith("91"):
        digits = "91" + digits

    return digits

# SAVE USER
async def save_user(user):
    if not user or not users:
        return
    try:
        await users.update_one(
            {"id": user.id},
            {"$set": {"name": user.first_name}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"save_user: {e}")

# BAN CHECK
async def is_banned(uid):
    if not banned_db:
        return False
    try:
        return bool(await banned_db.find_one({"id": uid}))
    except:
        return False

# API CALL
def get_number_info(number):
    try:
        url = f"https://api.apilayer.com/number_verification/validate?number={number}"

        headers = {
            "apikey": cfg.API_KEY
        }

        res = requests.get(url, headers=headers, timeout=10)

        if res.status_code != 200:
            return f"⚠️ API Error: {res.status_code}"

        data = res.json()
        print("API RESPONSE:", data)

        if not data.get("valid"):
            return "❌ Invalid / No Data Found"

        return (
            "🌍 TRUECALLER RESULT\n\n"
            f"📞 Number: <code>{data.get('international_format')}</code>\n"
            f"📌 Valid: <code>{data.get('valid')}</code>\n"
            f"📡 Carrier: <code>{data.get('carrier')}</code>\n"
            f"🌍 Country: <code>{data.get('country_name')}</code>\n"
            f"📍 Location: <code>{data.get('location')}</code>\n"
        )

    except requests.exceptions.Timeout:
        return "⚠️ API Timeout"
    except Exception as e:
        logger.error(e)
        return "⚠️ API Failed"

# START
@bot.on_message(filters.command("start"))
async def start(_, m: Message):
    await save_user(m.from_user)

    text = f"""👋 Hello {m.from_user.first_name}

🤖 I am Truecaller Info Bot
🚀 Status: 🟢 Online
⚡ Speed: Fast
🔐 Secure Bot

👇 Send number:
Ex: +911234567890"""

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Premium", callback_data="premium")]
    ])

    await m.reply_photo(
        photo="https://i.ibb.co/S4jWcS4v/7168219724-29166.jpg",
        caption=text,
        reply_markup=buttons
    )

# MAIN
@bot.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def main(_, m: Message):
    uid = m.from_user.id

    await save_user(m.from_user)

    if await is_banned(uid):
        return await m.reply_text("🚫 You are banned")

    num = clean_number(m.text)
    if not num:
        return await m.reply_text("❌ Invalid Number")

    now = time.time()

    if cooldown.get(uid, 0) > now:
        return await m.reply_text("⏳ Slow down!")

    cooldown[uid] = now + 2

    msg = await m.reply_text("🔍 Searching...")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, get_number_info, num)

    await msg.edit(result, parse_mode=enums.ParseMode.HTML)

# RUN
bot.run()
