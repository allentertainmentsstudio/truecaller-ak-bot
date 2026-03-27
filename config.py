from os import getenv

class Config:
    API_ID = int(getenv("API_ID"))
    API_HASH = getenv("API_HASH")
    BOT_TOKEN = getenv("BOT_TOKEN")
    MONGO_URI = getenv("MONGO_URI")
    OWNER_ID = int(getenv("OWNER_ID"))
    UPI_ID = getenv("UPI_ID", "971916880@ybl")
    # ✅ FIXED
    API_KEY = getenv("API_KEY", "41ecb7c71fe62512fad162c8800fc85e")
    
cfg = Config()
