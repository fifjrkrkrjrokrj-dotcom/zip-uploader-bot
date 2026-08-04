"""
config.py
---------
Saari settings yahan par hain. Environment variables se load hoti hain
(recommended for hosting). .env file bhi support karta hai (local dev ke liye).
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional hai, prod me env vars directly set hote hain

# ---------------- REQUIRED ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

# Owner ka Telegram numeric user ID (apna ID @userinfobot se le lo)
OWNER_ID = int(os.environ.get("OWNER_ID", "123456789"))

# Extra admins (owner ke alawa) — comma separated numeric IDs
# Example: ADMIN_IDS=111111,222222
_admin_env = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = {OWNER_ID} | {
    int(x.strip()) for x in _admin_env.split(",") if x.strip().isdigit()
}

# ---------------- BUTTONS / LINKS ----------------
SUPPORT_CHAT_URL = os.environ.get("SUPPORT_CHAT_URL", "https://t.me/mysupportgroup")
OWNER_URL = os.environ.get("OWNER_URL", "https://t.me/myusername")
UPDATES_CHANNEL_URL = os.environ.get("UPDATES_CHANNEL_URL", "https://t.me/myupdateschannel")
SOURCE_URL = os.environ.get("SOURCE_URL", "https://github.com/myusername/zip-extractor-bot")

# Bot ka apna username (bina @ ke) — "Add me to group" button ke liye
BOT_USERNAME = os.environ.get("BOT_USERNAME", "MyZipExtractorBot")

# ---------------- FORCE SUBSCRIBE ----------------
# Khali chhod do ("") agar force-subscribe nahi chahiye.
# FORCE_SUB_CHANNEL: channel ka @username ya -100 wali chat id (bot must be admin there)
FORCE_SUB_CHANNEL = os.environ.get("FORCE_SUB_CHANNEL", "")
FORCE_SUB_CHANNEL_URL = os.environ.get("FORCE_SUB_CHANNEL_URL", UPDATES_CHANNEL_URL)

# ---------------- OPTIONAL ----------------
# Logging channel (ID with -100 prefix) jahan bot activity/errors log honge.
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID", "")

# Bot Api ka default upload/download limit ~50MB hai. Apna local Bot API
# server host kiya ho to 2000 tak badha sakte ho.
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "50"))

# Ek zip me max kitni files bot bhejega (spam-protection)
MAX_FILES_TO_SEND = int(os.environ.get("MAX_FILES_TO_SEND", "100"))

# Zip-bomb protection: extract hone ke baad total uncompressed size ki limit
MAX_EXTRACTED_SIZE_MB = int(os.environ.get("MAX_EXTRACTED_SIZE_MB", "500"))

# Ek user ek time me kitne archives parallel-queue kar sakta hai
MAX_QUEUE_PER_USER = int(os.environ.get("MAX_QUEUE_PER_USER", "5"))

# Bot-wide max archives jo ek saath process ho rahe ho (worker slots)
MAX_CONCURRENT_EXTRACTIONS = int(os.environ.get("MAX_CONCURRENT_EXTRACTIONS", "3"))

# Rate limit: ek user do archives ke beech kam se kam itne second wait kare
RATE_LIMIT_SECONDS = int(os.environ.get("RATE_LIMIT_SECONDS", "10"))

# Password prompt kitni der wait kare (seconds) — expire ho jaye to job cancel
PASSWORD_TIMEOUT_SECONDS = int(os.environ.get("PASSWORD_TIMEOUT_SECONDS", "120"))

# Supported archive extensions
SUPPORTED_EXTENSIONS = (".zip", ".rar", ".7z", ".tar", ".tar.gz", ".tar.bz2")

# Folders
DOWNLOAD_DIR = "downloads"
EXTRACT_DIR = "extracted"
REZIP_DIR = "rezipped"

# ---------------- DATABASE (MongoDB) ----------------
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://myuser:mypassword@cluster0.xxxxx.mongodb.net/")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "zip_extractor_bot")
