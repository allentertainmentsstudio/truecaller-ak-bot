import re
import asyncio
from truecallerpy import search_phonenumber
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from configs import cfg

bot = Client(
    "ultra_truecaller",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    bot_token=cfg.BOT_TOKEN
)

OWNER = cfg.SUDO
LOG_ID = cfg.LOGCHID
cc = cfg.API

# ───────── MONGO ───────── #
mongo = AsyncIOMotorClient(cfg.MONGO_URI)
db = mongo["truecaller_bot"]
users_col = db["users"]
cache_col = db["cache"]
ban_col = db["banned"]

# ───────── RATE LIMIT ───────── #
user_limit = {}

# ───────── CLEAN NUMBER ───────── #
def clean_number(n: str):
    n = n.strip().replace(" ", "")

    if n.startswith("+"):
        return n

    if n.startswith("00"):
        return "+" + n[2:]

    digits = re.sub(r"\D", "", n)

    if len(digits) < 8:
        return None

    return digits


# ───────── UI BUTTON ───────── #
def buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Try Again", callback_data="retry")]
    ])


# ───────── FETCH ───────── #
async def fetch(num, msg: Message):
    try:
        if not num:
            return await msg.edit("❌ Invalid Number")

        # CACHE CHECK
        cached = await cache_col.find_one({"num": num})
        if cached:
            return await msg.edit(cached["data"], parse_mode=enums.ParseMode.HTML)

        r = search_phonenumber(num, None, cc)

        data = r["data"][0]
        phone = data["phones"][0]
        addr = data.get("addresses", [{}])[0]

        text = f"""
👤 Name: <code>{data.get('name','N/A')}</code>
📞 Number: <code>{phone.get('nationalFormat',num)}</code>
📌 Type: <code>{phone.get('numberType','N/A')}</code>
🌍 Country: <code>{phone.get('countryCode','N/A')}</code>
📡 Carrier: <code>{phone.get('carrier','N/A')}</code>
⏳ Timezone: <code>{addr.get('timeZone','N/A')}</code>
"""

        # SAVE CACHE
        await cache_col.insert_one({"num": num, "data": text})

        await msg.edit(text, reply_markup=buttons(), parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await msg.edit("⚠️ Not Found / Error")
        await bot.send_message(LOG_ID, str(e))


# ───────── BAN CHECK ───────── #
async def is_banned(uid):
    return await ban_col.find_one({"id": uid})


# ───────── START ───────── #
@bot.on_message(filters.command("start"))
async def start(_, m: Message):
    await users_col.update_one(
        {"id": m.from_user.id},
        {"$set": {"id": m.from_user.id}},
        upsert=True
    )
    await m.reply_text("👋 Send any number to get info.")


# ───────── MAIN ───────── #
@bot.on_message(filters.text & filters.private)
async def main(_, m: Message):
    uid = m.from_user.id

    # BAN CHECK
    if await is_banned(uid):
        return await m.reply_text("🚫 You are banned.")

    # RATE LIMIT (5 sec)
    if uid in user_limit:
        if asyncio.get_event_loop().time() - user_limit[uid] < 5:
            return await m.reply_text("⏳ Slow down!")
    user_limit[uid] = asyncio.get_event_loop().time()

    num = clean_number(m.text)
    msg = await m.reply_text("⚡ Processing...")
    await fetch(num, msg)


# ───────── CALLBACK ───────── #
@bot.on_callback_query(filters.regex("retry"))
async def retry(_, cb):
    await cb.message.edit("Send number again.")


# ───────── STATS ───────── #
@bot.on_message(filters.command("stats") & filters.user(OWNER))
async def stats(_, m: Message):
    u = await users_col.count_documents({})
    c = await cache_col.count_documents({})
    b = await ban_col.count_documents({})

    await m.reply_text(
        f"📊 BOT STATS\n\n👤 Users: {u}\n💾 Cache: {c}\n🚫 Banned: {b}"
    )


# ───────── BAN ───────── #
@bot.on_message(filters.command("ban") & filters.user(OWNER))
async def ban(_, m: Message):
    if not m.reply_to_message:
        return await m.reply_text("Reply to user")

    uid = m.reply_to_message.from_user.id
    await ban_col.insert_one({"id": uid})
    await m.reply_text("🚫 User banned")


# ───────── UNBAN ───────── #
@bot.on_message(filters.command("unban") & filters.user(OWNER))
async def unban(_, m: Message):
    if not m.reply_to_message:
        return await m.reply_text("Reply to user")

    uid = m.reply_to_message.from_user.id
    await ban_col.delete_one({"id": uid})
    await m.reply_text("✅ User unbanned")


print("🚀 ULTRA BOT RUNNING")
bot.run()
