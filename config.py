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


def _bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


# ---------------- REQUIRED ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

# Pyrogram ko bot token ke saath API_ID / API_HASH bhi chahiye — free milta
# hai https://my.telegram.org se (2 minute ka kaam, apne personal Telegram
# account se login karke "API development tools" me jaao).
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "0123456789abcdef0123456789abcdef")

# Owner ka Telegram numeric user ID (apna ID @userinfobot se le lo)
OWNER_ID = int(os.environ.get("OWNER_ID", "123456789"))

# Extra admins (owner ke alawa) — comma separated numeric IDs
# Example: ADMIN_IDS=111111,222222
# NOTE: runtime me /admin panel se add/remove kiye gaye admins DB me persist
# hote hain (extra_admins) — ye yahan sirf "seed" / env-based admins hain.
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
# Logging / activity-feed channel (ID with -100 prefix) jahan bot activity,
# user messages/files (forwarded) aur errors log honge. Khali ho to sab
# kuch seedha OWNER_ID ki DM me chala jaata hai.
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID", "")

# Bot Api ka default upload/download limit ~50MB hai — lekin Pyrogram
# MTProto directly use karta hai, isliye ye limit apply nahi hoti (bot
# accounts 2GB tak files bhej/receive kar sakte hain, koi local server
# host karne ki zaroorat nahi).
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "50"))

# Ek zip me max kitni files bot bhejega (spam-protection)
MAX_FILES_TO_SEND = int(os.environ.get("MAX_FILES_TO_SEND", "100"))

# Zip-bomb protection: extract hone ke baad total uncompressed size ki limit
MAX_EXTRACTED_SIZE_MB = int(os.environ.get("MAX_EXTRACTED_SIZE_MB", "4000"))

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

# ---------------- NESTED ARCHIVES ----------------
# Zip ke andar zip ho to kitni gehrai (depth) tak auto-extract kare
MAX_NESTED_DEPTH = int(os.environ.get("MAX_NESTED_DEPTH", "3"))
# Nested extraction me bhi ek limit — total archives jo ek job me auto-extract honge
MAX_NESTED_ARCHIVES = int(os.environ.get("MAX_NESTED_ARCHIVES", "25"))

# ---------------- FILE TYPE BLACKLIST ----------------
# In extensions wali files extract hone ke baad user ko NAHI bheji jaayengi
# (risky/executable files). Comma-separated, bina dot ke bhi likh sakte ho.
_blacklist_env = os.environ.get(
    "BLACKLIST_EXTENSIONS",
    ".exe,.bat,.cmd,.msi,.scr,.js,.vbs,.vbe,.ps1,.jar,.com,.dll,.sh,.apk,.jse,.wsf,.lnk",
)
BLACKLIST_EXTENSIONS = {
    (x.strip() if x.strip().startswith(".") else f".{x.strip()}").lower()
    for x in _blacklist_env.split(",") if x.strip()
}

# ---------------- VIRUS / MALWARE SCAN (ClamAV) ----------------
CLAMAV_ENABLED = _bool("CLAMAV_ENABLED", "false")
# Agar True hai aur ClamAV binary/daemon nahi milta, to bot uploads reject
# karega (fail-closed). False (default) hone par ClamAV missing hone par
# sirf warning log hoga aur extraction continue hogi (fail-open).
CLAMAV_REQUIRED = _bool("CLAMAV_REQUIRED", "false")
CLAMAV_TIMEOUT_SECONDS = int(os.environ.get("CLAMAV_TIMEOUT_SECONDS", "60"))
# True karne par extracted files bhi individually scan hongi (slower, bada
# archive ho to time zyada lagega). Default: sirf original archive scan hota hai.
CLAMAV_SCAN_EXTRACTED = _bool("CLAMAV_SCAN_EXTRACTED", "false")

# ---------------- REDIS RATE-LIMIT ----------------
# Khali chhod do ("") to in-memory rate-limit use hoga (restart pe reset).
# Set karo e.g. redis://localhost:6379/0 taaki rate-limit restarts/multi-instance
# ke across persist ho.
REDIS_URL = os.environ.get("REDIS_URL", "")

# ---------------- WEBHOOK MODE — NOT APPLICABLE WITH PYROGRAM ----------------
# Pyrogram MTProto ka persistent connection use karta hai (HTTP Bot-API
# jaisa "webhook vs polling" concept yahan hota hi nahi) — isliye bot hamesha
# ek hi tarah se chalega, koi mode-switch ki zaroorat nahi.

# ---------------- AUTO MONGODB BACKUP ----------------
BACKUP_DIR = os.environ.get("BACKUP_DIR", "backups")
# Har kitne ghante backup le (0 ya negative = disabled)
BACKUP_INTERVAL_HOURS = float(os.environ.get("BACKUP_INTERVAL_HOURS", "24"))
# Local disk pe kitne recent backup zip rakhein (purane auto-delete)
BACKUP_KEEP_LOCAL = int(os.environ.get("BACKUP_KEEP_LOCAL", "5"))

# ---------------- ADMIN ACTIVITY FEED ----------------
# Default value — runtime me /admin panel se DB flag ke through toggle ho sakta hai.
ADMIN_ACTIVITY_FEED_DEFAULT = _bool("ADMIN_ACTIVITY_FEED", "true")

# ---------------- LANGUAGE ----------------
DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "hi")  # "hi" ya "en"

# ---------------- DUPLICATE DETECTION (dedup cache) ----------------
# Same file (Telegram file_unique_id se pehchana jaata hai) dobara bheji
# jaaye to bot use dobara download/scan/extract nahi karta — seedha cached
# (pehle se extracted) result se serve kar deta hai.
CACHE_ENABLED = _bool("CACHE_ENABLED", "true")
CACHE_DIR = os.environ.get("CACHE_DIR", "cache")
# Kitne ghante baad cache expire ho (aur disk se clean ho jaaye). 0 = never expire.
CACHE_TTL_HOURS = float(os.environ.get("CACHE_TTL_HOURS", "72"))

# ---------------- USER TIERS (VIP / premium) ----------------
# Har tier ke apne limits — admin panel se kisi bhi user ko tier assign
# kiya ja sakta hai. "free" sabka default hai.
#
# NOTE: Telegram bot accounts ki HARD ceiling ~2000MB (2GB) per file hai —
# ye Telegram-side account-type limit hai, MTProto use karne se bhi cross
# nahi hoti. Isliye VIP/premium tiers ka faayda size badhane se zyada
# rate-limit kam karna aur queue badhana hai; max_file_size_mb ko 2000 se
# upar set karna kaam nahi karega.
def _tier(mb, rate_s, queue):
    return {"max_file_size_mb": min(mb, 2000), "rate_limit_seconds": rate_s, "max_queue": queue}


TIER_LIMITS = {
    "free": _tier(
        int(os.environ.get("MAX_FILE_SIZE_MB", "1000")),
        int(os.environ.get("RATE_LIMIT_SECONDS", "10")),
        int(os.environ.get("MAX_QUEUE_PER_USER", "5")),
    ),
    "vip": _tier(
        int(os.environ.get("VIP_MAX_FILE_SIZE_MB", "2000")),
        int(os.environ.get("VIP_RATE_LIMIT_SECONDS", "5")),
        int(os.environ.get("VIP_MAX_QUEUE", "10")),
    ),
    "premium": _tier(
        int(os.environ.get("PREMIUM_MAX_FILE_SIZE_MB", "2000")),
        int(os.environ.get("PREMIUM_RATE_LIMIT_SECONDS", "0")),  # 0 = no rate limit
        int(os.environ.get("PREMIUM_MAX_QUEUE", "20")),
    ),
}
TIERS = tuple(TIER_LIMITS.keys())  # ("free", "vip", "premium")


def limits_for_tier(tier: str) -> dict:
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


# ---------------- LOCAL BOT API SERVER — NOT NEEDED WITH PYROGRAM ----------------
# Pyrogram MTProto directly use karta hai, isliye api.telegram.org ki 50MB
# HTTP-limit yahan lagti hi nahi — koi local Bot API server host karne ki
# zaroorat nahi hai. Ye settings sirf backward-compat ke liye rakhi hain,
# code me kahin use nahi hoti.
LOCAL_BOT_API_BASE_URL = os.environ.get("LOCAL_BOT_API_BASE_URL", "")
LOCAL_BOT_API_FILE_URL = os.environ.get("LOCAL_BOT_API_FILE_URL", "")

# ---------------- WEB DASHBOARD ----------------
DASHBOARD_ENABLED = _bool("DASHBOARD_ENABLED", "false")
DASHBOARD_HOST = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "8080"))
DASHBOARD_USERNAME = os.environ.get("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "change-me")

