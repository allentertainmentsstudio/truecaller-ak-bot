from os import getenv
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(getenv("API_ID", 0))
    API_HASH = getenv("API_HASH", "")
    BOT_TOKEN = getenv("BOT_TOKEN", "")
    MONGO_URI = getenv("MONGO_URI", "")
    OWNER_ID = int(getenv("OWNER_ID", 0))

    UPI_ID = getenv("UPI_ID", "971916880@ybl")
    API_KEY = getenv("API_KEY")

cfg = Config()
