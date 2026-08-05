# 📦 Archive Extractor Telegram Bot — Pro Edition (v4, Pyrogram/MTProto)

Telegram bot jo ZIP, RAR, 7Z aur TAR files ko **safely** extract karke andar ki
saari files wapas bhej deta hai — ya ek naye ZIP me pack karke. v4 me bot ka
core engine **Pyrogram (MTProto)** pe migrate ho gaya hai — isse ab **files
2GB tak** seedha bhej/receive ho sakti hain, koi local Bot-API server host
karne ki zaroorat nahi (v3 me `python-telegram-bot` use hota tha, jiski HTTP
Bot-API 50MB tak limited thi).

> **Kya same raha, kya badla:** Extraction/security logic (`security.py`),
> database (`database.py`), ClamAV scan, dedup cache, backups, i18n — sab
> **bilkul same** hai. Sirf Telegram se "baat karne ka tareeka" (main.py,
> admin.py, notify.py, backup.py ke Telegram-facing parts) Pyrogram ke
> hisaab se dobara likha gaya hai.

## ✨ User-facing features

| Feature | Kya karta hai |
|---|---|
| **Archive bhejo** | `.zip .rar .7z .tar .tar.gz .tar.bz2` bhejo, **2GB tak** |
| **Real preview-before-extract** | Extraction se pehle files ki list + size dikhta hai |
| **Duplicate detection** | Same file dobara bheji to instant cached preview — download/scan/extract skip |
| **Nested archive support** | Zip ke andar zip auto-extract |
| **Virus/malware scan (ClamAV)** | Extraction se pehle scan |
| **File-type blacklist** | `.exe .bat` jaisi risky files auto-skip |
| **Real multi-language (Hindi/English)** | Poora UI translate hota hai |
| **User tiers (Free / VIP / Premium)** | Har tier ka apna rate-limit/queue-limit |
| **Per-user history (`/history`)** | |
| **Password-protected archives** | Bot khud reply-message me maangega |
| **Queue, force-subscribe, Redis rate-limit, `/cancel`** | |

## 🛡️ Admin-facing (`/admin`)

Analytics, ban/unban, add/remove admin, set user tier, maintenance mode,
activity feed toggle, broadcast now (text/photo/document/video — sab
chalega), scheduled broadcast (`/schedulebroadcast`), `/logs`, manual/auto
MongoDB backup, "delete all sent files" panic button, aur web dashboard —
sab pichle version jaisa hi hai, koi feature nahi hataya.

## 📏 File-size — ab sach me 2GB tak

Pyrogram bot ke liye direct MTProto connection use karta hai (Telegram ka
raw protocol) — HTTP Bot-API wrapper ke bajaye. Isse **Telegram-wide hard
ceiling ~2GB (2000MB) per file** tak files chalti hain, **bina koi extra
server host kiye.** `.env` me `MAX_FILE_SIZE_MB` / `VIP_MAX_FILE_SIZE_MB` /
`PREMIUM_MAX_FILE_SIZE_MB` set karo — 2000 se upar set karne ka koi fayda
nahi, Telegram khud ussey bada file allow nahi karega (koi bhi library ho).

## 🛠 Setup

### 1. API_ID / API_HASH lo (naya step, Pyrogram ke liye zaroori)
1. https://my.telegram.org par jaao, apne **personal** Telegram account se login karo
2. "API development tools" click karo
3. Koi bhi App title/short name daal do (kuch bhi, matter nahi karta)
4. `api_id` aur `api_hash` mil jaayenge — `.env` me daal do

### 2. Bot Token
BotFather se jaisa pehle liya tha, wahi `BOT_TOKEN` reuse hoga.

### 3. Dependencies
```bash
pip install -r requirements.txt
```
- RAR support: `sudo apt install unrar` (ya `unar`)
- Virus scan (optional): `sudo apt install clamav clamav-daemon && sudo freshclam`
- Redis (optional): local ya managed (Upstash free tier)
- `tgcrypto` (Pyrogram ki speed-optimized crypto) — pip se hi install ho
  jaata hai, isके liye C compiler chahiye ho sakta hai (Docker image me
  `build-essential` already included hai)

### 4. Config
`.env.example` → `.env` copy karo, sab values bharo (`BOT_TOKEN`, `API_ID`,
`API_HASH`, `OWNER_ID`, `MONGO_URI`, waghera).

### 5. Chalao
```bash
python main.py
```
Pehli baar chalane par Pyrogram ek `zipbot.session` file banayega (login
session cache) — isse restart pe dobara authenticate nahi karna padta.

## 🚀 Railway pe deploy

Railway pe bina kisi extra setup ke chal jaata hai — Pyrogram normal Python
process hai, koi webhook/port-binding zaroori nahi (dashboard alag baat hai,
neeche dekho):

1. Repo ko Railway se connect karo (ya `railway up` CLI se)
2. Railway ke **Variables** tab me `.env.example` ke sab keys env variables
   ke roop me add karo — khaaskar `BOT_TOKEN`, `API_ID`, `API_HASH`,
   `OWNER_ID`, `MONGO_URI`
3. Railway apne-aap `requirements.txt` detect karke install karega, aur
   `Procfile` (`worker: python main.py`) se process start hoga
4. **Persistent storage:** Railway ka filesystem ephemeral hai — `zipbot.session`,
   `cache/`, `downloads/` waghera restart pe reset ho jaate hain. Chhoti-si
   bot ke liye ye theek hai (session dobara ban jaata hai, cache dobara
   populate ho jaata hai), lekin agar persistence chahiye to Railway Volume
   mount kar lo (`downloads/extracted/rezipped/backups/cache` folders ke liye)
5. `DASHBOARD_ENABLED=true` kiya ho to Railway apne-aap `PORT` env var deta
   hai — agar Railway ka diya hua port use karna ho to `.env` me
   `DASHBOARD_PORT` ko `${PORT}` se map kar do (ya bas dashboard disable
   rakho agar zaroori nahi)
6. MongoDB ke liye [MongoDB Atlas](https://www.mongodb.com/atlas) free tier
   use kar sakte ho (`MONGO_URI` wahi daalo)

## 🔒 Security

Zip-slip / path-traversal protection, zip-bomb protection, nested-archive
safety limits, file-type blacklist, ClamAV scan, per-job temp folders,
global error handling, dashboard HTTP Basic-Auth — sab pehle jaisa hi hai.

## 📁 Project Structure

```
zipbot/
├── main.py           # Entry point — Pyrogram Client, handlers, queue, preview→extract flow
├── admin.py          # Admin panel (Pyrogram CallbackQuery/Message based)
├── state.py          # Per-user ephemeral flow-state (PTB ke context.user_data ka replacement)
├── security.py       # Safe extraction, nested-archive, preview listing, blacklist, re-zip
├── dedup.py           # Duplicate-file detection + cache management
├── dashboard.py         # FastAPI web dashboard (Telegram library se independent)
├── clamav.py             # ClamAV virus/malware scan wrapper
├── notify.py               # Admin activity feed (Pyrogram client-based)
├── backup.py                 # Scheduled + manual MongoDB backup
├── logbuffer.py                # In-memory log ring buffer for /logs
├── i18n.py                       # Real Hindi/English translations
├── config.py                      # Saari settings incl. API_ID/API_HASH, tier limits
├── database.py                      # MongoDB — users, tiers, history, cache, etc.
├── ratelimit.py                       # Redis-backed, tier-aware cooldown
├── utils.py                             # Display formatting helpers
├── requirements.txt
├── .env.example
├── Dockerfile / docker-compose.yml / Procfile / .gitignore
```

## ⚠️ Limits & notes

- File-size ceiling ~2GB, Telegram-wide hard limit (koi library ise cross nahi kar sakti).
- `MAX_FILES_TO_SEND` (default 100) se zyada files hongi to sirf pehli itni hi.
- Duplicate-cache disk space use karta hai — `CACHE_TTL_HOURS` se control karo.
- "Delete all sent files" permanent hai, undo nahi ho sakta.
- Pyrogram ka `.session` file sensitive hai (isme login credentials cached
  hain) — `.gitignore` me already excluded hai, kabhi commit/share mat karo.
- Web dashboard same asyncio process me chalta hai; production me HTTPS
  reverse-proxy (nginx/Caddy) laga lena behtar hai.

## 🚀 Hosting (general)

VPS, Railway, Render, ya apne PC pe bhi chal jaata hai — Pyrogram ek normal
persistent connection maintain karta hai (koi webhook/polling mode-switch
ki zaroorat nahi, jo `python-telegram-bot` me hota tha). 24/7 ke liye Docker
(`docker compose up -d`) ya `systemd` service recommended hai.
