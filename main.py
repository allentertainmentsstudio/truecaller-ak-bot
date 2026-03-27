import re, time, asyncio, logging, signal, sys, os
from collections import OrderedDict, defaultdict

from truecallerpy import search_phonenumber
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# CONFIG FROM ENV
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
API = os.getenv("API")
OWNER_ID = int(os.getenv("OWNER_ID"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# BOT
bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=20)

# DB
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo["truecaller"]

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
    def get(self, key): return self.cache.get(key)
    def set(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

cache = LRUCache()
cache_lock = asyncio.Lock()

# FLAGS
flags = {"IN":"🇮🇳","US":"🇺🇸","GB":"🇬🇧"}
def get_flag(c): return flags.get((c or "").upper(),"🌍")

# CLEAN NUMBER
def clean_number(n):
    if not n: return None
    n = n.strip().replace(" ","")
    if n.startswith("+"): return n
    if n.startswith("00"): return "+"+n[2:]
    digits = re.sub(r"\D","",n)
    return digits if 8<=len(digits)<=15 else None

# AI SPAM
user_activity = defaultdict(list)
user_score = defaultdict(int)
temp_ban = {}

async def spam_check(uid, num, premium):
    now = time.time()
    user_activity[uid].append((num, now))
    user_activity[uid] = [(n,t) for n,t in user_activity[uid] if now-t<10]

    score = 0
    if len(user_activity[uid]) > (8 if premium else 5): score+=3
    if [n for n,_ in user_activity[uid]].count(num) > 3: score+=3
    if num is None: score+=2

    user_score[uid]+=score
    return user_score[uid]

async def check_temp(uid):
    if uid in temp_ban and time.time()<temp_ban[uid]:
        return True
    temp_ban.pop(uid,None)
    return False

# DB HELPERS
async def save_user(u):
    if u:
        await users.update_one({"id":u.id},{"$set":{"name":u.first_name}},upsert=True)

async def is_premium(uid):
    return bool(await premium_db.find_one({"id":uid}))

async def is_banned(uid):
    return bool(await banned_db.find_one({"id":uid}))

# SEARCH
async def search(num):
    return await asyncio.wait_for(
        asyncio.to_thread(search_phonenumber, num, None, API),
        timeout=10
    )

# FETCH
async def fetch(num, msg):
    async with sem:
        async with cache_lock:
            c = cache.get(num)
            if c: return await msg.edit(c)

        data = await search(num)
        if not data or not data.get("data"):
            return await msg.edit("❌ No Data")

        d = data["data"][0]
        phone = (d.get("phones") or [{}])[0]

        text = (
            f"🌍 TRUECALLER RESULT\n\n"
            f"👤 {d.get('name','N/A')}\n"
            f"📞 {phone.get('nationalFormat','N/A')}\n"
            f"📡 {phone.get('carrier','N/A')}"
        )

        async with cache_lock:
            cache.set(num, text)

        await msg.edit(text)

# START PANEL
@bot.on_message(filters.command("start"))
async def start(_, m):
    await save_user(m.from_user)

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search", callback_data="search")],
        [InlineKeyboardButton("💎 Plan", callback_data="plan"),
         InlineKeyboardButton("👤 Profile", callback_data="profile")]
    ])

    await m.reply_text("🚀 Bot Ready", reply_markup=btn)

# BUTTONS
@bot.on_callback_query()
async def cb(_, q):
    uid = q.from_user.id

    if q.data=="search":
        await q.message.edit("📞 Send number")

    elif q.data=="plan":
        p = await is_premium(uid)
        await q.message.edit("💎 Premium" if p else "❌ Free")

    elif q.data=="profile":
        await q.message.edit(f"🆔 {uid}")

# BROADCAST
@bot.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast(_, m):
    if not m.reply_to_message and len(m.command) < 2:
        return await m.reply_text("❌ Give message")

    msg = m.reply_to_message or m
    success = failed = 0

    async for u in users.find({}):
        try:
            if m.reply_to_message:
                await msg.copy(u["id"])
            else:
                await bot.send_message(u["id"], m.text.split(None,1)[1])
            success+=1
            await asyncio.sleep(0.05)
        except:
            failed+=1

    await m.reply_text(f"✅ Done\nSuccess:{success}\nFailed:{failed}")

# STATS
@bot.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def stats(_, m):
    await m.reply_text(
        f"👤 Users: {await users.count_documents({})}\n"
        f"💎 Premium: {await premium_db.count_documents({})}\n"
        f"🚫 Banned: {await banned_db.count_documents({})}\n"
        f"📞 Searches: {await logs.count_documents({})}"
    )

# MAIN
@bot.on_message(filters.private & filters.text & ~filters.command(["start","broadcast","stats"]))
async def main(_, m):
    uid = m.from_user.id
    await save_user(m.from_user)

    if await is_banned(uid):
        return await m.reply_text("🚫 Banned")

    if await check_temp(uid):
        return await m.reply_text("⛔ Temp Block")

    num = clean_number(m.text)
    premium = await is_premium(uid)

    score = await spam_check(uid, num, premium)

    if score >= 10:
        await banned_db.insert_one({"id":uid})
        return await m.reply_text("🚫 Permanent Ban")

    if score >= 6:
        temp_ban[uid] = time.time()+60
        return await m.reply_text("⛔ Temp Ban")

    if not num:
        return await m.reply_text("❌ Invalid")

    now = time.time()
    async with cooldown_lock:
        if cooldown.get(uid,0) > now:
            return await m.reply_text("⏳ Slow down")
        cooldown[uid] = now + (1 if premium else 2)

    msg = await m.reply_text("🔍 Searching...")
    await fetch(num, msg)

# RUN
bot.run()
    n = n.strip().replace(" ", "")

    if n.startswith("+"):
        return n

    if n.startswith("00"):
        return "+" + n[2:]

    digits = re.sub(r"\D", "", n)
    return digits if 8 <= len(digits) <= 15 else None


# ───────── NON-BLOCKING API CALL ───────── #
async def search_async(num):
    return await asyncio.to_thread(search_phonenumber, num, None, cc)


# ───────── SAVE USER ───────── #
async def save_user(user):
    if not user:
        return

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
    try:
        await logs.insert_one({
            "user_id": uid,
            "number": num,
            "time": time.time()
        })
    except:
        pass


# ───────── FETCH (WITH SEMAPHORE LIMIT) ───────── #
async def fetch(num, msg: Message, user):
    async with sem:   # 🔥 concurrency limit applied

        try:
            data = await search_async(num)

            if not data or not data.get("data"):
                return await msg.edit("❌ No Data Found")

            d = data["data"][0]

            phone = (d.get("phones") or [{}])[0]
            addr = (d.get("addresses") or [{}])[0]

            code = phone.get("countryCode", "N/A")
            flag = get_flag(code)

            text = (
                "🌍 TRUECALLER RESULT\n\n"
                f"👤 Name: <code>{d.get('name','N/A')}</code>\n"
                f"📞 Number: <code>{phone.get('nationalFormat', num)}</code>\n"
                f"📌 Type: <code>{phone.get('numberType','N/A')}</code>\n"
                f"🌍 Country: {flag} <code>{code}</code>\n"
                f"📡 Carrier: <code>{phone.get('carrier','N/A')}</code>\n"
                f"⏳ Timezone: <code>{addr.get('timeZone','N/A')}</code>\n\n"
                "⚡ Status: SUCCESS"
            )

            await save_log(user.id, num)
            await msg.edit(text, parse_mode=enums.ParseMode.HTML)

        except Exception as e:
            await msg.edit(f"⚠️ Error\n<code>{str(e)}</code>")


# ───────── START ───────── #
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

    if cooldown.get(uid, 0) > now:
        return await m.reply_text("⏳ Slow down!")

    cooldown[uid] = now + 3

    num = clean_number(m.text)

    if not num:
        return await m.reply_text("❌ Invalid Number")

    msg = await m.reply_text("🔍 Searching...")

    await fetch(num, msg, m.from_user)


print("🚀 TRUECALLER BOT RUNNING (SEMAPHORE + PRO OPTIMIZED)")
bot.run()
