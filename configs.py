import os

class cfg:
    API_ID = int(os.getenv("API_ID", "1234567"))
    API_HASH = os.getenv("API_HASH", "your_api_hash")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")
    API = os.getenv("API", "IN")
    MONGO_URI = os.getenv("MONGO_URI", "your_mongodb_url")
    OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
