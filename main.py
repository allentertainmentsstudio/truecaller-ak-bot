import re
import time
from truecallerpy import search_phonenumber
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
from configs import cfg

# ───────── BOT SETUP ───────── #
bot = Client(
    "truecaller_saas_bot",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    bot_token=cfg.BOT_TOKEN
)

cc = cfg.API

# ───────── DATABASE ───────── #
mongo = AsyncIOMotorClient(cfg.MONGO_URI)
db = mongo["truecaller"]

users = db["users"]
logs = db["logs"]

# ───────── CACHE ───────── #
cooldown = {}

# ───────── FLAGS ───────── #
flags = {
    "IN": "🇮🇳",
    "US": "🇺🇸",
    "GB": "🇬🇧",
    "AE": "🇦🇪",
    "PK": "🇵🇰",
    "BD": "🇧🇩"
}

def get_flag(code):
    return flags.get((code or "").upper(), "🌍")


# ───────── CLEAN NUMBER ───────── #
def clean_number(n: str):
    n = n.strip().replace(" ", "")

    if n.startswith("+"):
        return n

    if n.startswith("00"):
        return "+" + n[2:]

    digits = re.sub(r"\D", "", n)
    return digits if len(digits) >= 8 else None


# ───────── SAVE USER ───────── #
async def save_user(user):
    await users.update_one(
        {"id": user.id},
        {"$set": {
            "name": user.first_name,
            "username": user.username
        }},
        upsert=True
    )


# ───────── SAVE LOG ───────── #
async def save_log(uid, num):
    await logs.insert_one({
        "user_id": uid,
        "number": num,
        "time": time.time()
    })


# ───────── FETCH TRUECALLER DATA ───────── #
async def fetch(num, msg: Message, user):
    try:
        data = search_phonenumber(num, None, cc)

        if not data or not data.get("data"):
            return await msg.edit("❌ No Data Found")

        d = data["data"][0]

        phone = (d.get("phones") or [{}])[0]
        addr = (d.get("addresses") or [{}])[0]

        code = phone.get("countryCode", "N/A")
        flag = get_flag(code)

        text = f"""
🌍 TRUECALLER RESULT

👤 Name: <code>{d.get('name','N/A')}</code>
📞 Number: <code>{phone.get('nationalFormat', num)}</code>
📌 Type: <code>{phone.get('numberType','N/A')}</code>
🌍 Country: {flag} <code>{code}</code>
📡 Carrier: <code>{phone.get('carrier','N/A')}</code>
⏳ Timezone: <code>{addr.get('timeZone','N/A')}</code>

⚡ Status: SUCCESS
"""

        await save_log(user.id, num)
        await msg.edit(text, parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await msg.edit(
            f"⚠️ Error Occurred\n\n<code>{str(e)}</code>"
        )


# ───────── START COMMAND ───────── #
@bot.on_message(filters.command("start"))
async def start(_, m: Message):
    await save_user(m.from_user)

    await m.reply_text(
        "🚀 Truecaller Bot Ready\n\n📞 Send any number to get details"
    )


# ───────── MAIN HANDLER ───────── #
@bot.on_message(filters.private & filters.text)
async def main(_, m: Message):
    await save_user(m.from_user)

    uid = m.from_user.id
    now = time.time()

    # cooldown
    if uid in cooldown and now - cooldown[uid] < 3:
        return await m.reply_text("⏳ Slow down!")

    cooldown[uid] = now

    num = clean_number(m.text)

    if not num:
        return await m.reply_text("❌ Invalid Number")

    msg = await m.reply_text("🔍 Searching database...")

    await fetch(num, msg, m.from_user)


print("🚀 TRUECALLER BOT RUNNING (FIXED + STABLE)")
bot.run()
