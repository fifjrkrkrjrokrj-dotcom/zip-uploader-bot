# 📦 Archive Extractor Telegram Bot — Professional Edition

Telegram bot jo ZIP, RAR, 7Z aur TAR files ko **safely** extract karke andar ki
saari files wapas bhej deta hai — ya ek naye ZIP me pack karke.

## ✨ Features (kis se kya hota hai)

### User-facing
| Feature | Kya karta hai |
|---|---|
| **Archive bhejo** | `.zip .rar .7z .tar .tar.gz .tar.bz2` bhejo, bot download → extract → preview karega |
| **Preview + choose format** | Extract hone ke baad file-list aur total size dikhta hai, phir 3 button: **✅ Send Files** (har file alag), **🗜 Send as ZIP** (sab ek zip me), **❌ Cancel** |
| **Password-protected archives** | Agar zip/rar/7z locked hai, bot khud reply-message me password maangega (message auto-delete ho jaata hai privacy ke liye) |
| **Multiple archives / queue** | Ek user do-teen archives ek saath bheje to sab queue me lagti hain, ek-ek karke process hoti hain (position bhi dikhta hai) |
| **Force-subscribe** | Agar `FORCE_SUB_CHANNEL` set hai, to user pehle channel join kare tabhi bot use kar payega — "🔔 Join" + "✅ I've Joined" buttons ke saath |
| **Rate limiting** | Har user do archives ke beech `RATE_LIMIT_SECONDS` wait kare — spam se bachne ke liye |
| **/cancel** | Chal rahi ya pending job (queue / password-wait) turant cancel |
| **Colored inline buttons** | Bot API 9.4 (Feb 2026) — success (green) / primary (blue) / danger (red) |

### Admin-facing (`/admin` — sirf `OWNER_ID` + `ADMIN_IDS`)
| Button | Kya karta hai |
|---|---|
| **📊 Analytics** | Total users, banned count, total extractions, total files sent, aaj ke active users/extractions, last-7-days summary |
| **🚫 Ban user** | Numeric Telegram user ID maangta hai, ban kar deta hai — banned user ki koi bhi file silently ignore hoti hai |
| **✅ Unban user** | Wahi user wapas unban |
| **🛠 Maintenance mode** | ON karne pe normal users ko "bot maintenance me hai" milta hai, admins bot use karte reh sakte hain |
| **📢 Broadcast** | `/broadcast <message>` — sabhi (non-banned) users ko batched + flood-safe tarike se bhejta hai |

## 🔒 Security (naye upgrades)

- **Zip-slip / path-traversal protection** — koi bhi archive member jo `extract_dir` ke bahar likhne ki koshish kare (`../../etc/passwd` jaisa), turant reject ho jaata hai.
- **Zip-bomb protection** — extraction se *pehle* total uncompressed size check hoti hai (`MAX_EXTRACTED_SIZE_MB`), limit se zyada hui to extract hi nahi hota.
- **Per-job unique temp folders** (UUID-based) — concurrent uploads ek dusre se clash nahi karte.
- **Global error handler** — koi bhi unhandled exception bot ko crash nahi karega, sirf log hoga (aur agar `LOG_CHANNEL_ID` set hai to wahan bhi).

## 🛠 Setup

1. **Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   RAR support ke liye system binary bhi chahiye: `sudo apt install unrar` (ya `unar`).

2. **Config:** `.env.example` ko `.env` me copy karo aur values bharo (ya seedha environment variables set karo — hosting ke liye recommended).
   - `BOT_TOKEN`, `OWNER_ID` — required
   - `ADMIN_IDS` — comma-separated extra admins (optional)
   - `FORCE_SUB_CHANNEL` — khali chhodo agar nahi chahiye
   - `MONGO_URI` — MongoDB Atlas free tier se milta hai (README ke purane version me steps hain)

3. **Chalao:**
   ```bash
   python main.py
   ```
   ya Docker se:
   ```bash
   docker compose up -d --build
   ```

## 📁 Project Structure

```
zipbot/
├── main.py          # Entry point — sab handlers, queue, password-flow
├── admin.py          # Admin panel (analytics, ban/unban, maintenance)
├── security.py        # Safe extraction, zip-bomb/zip-slip protection, re-zip
├── config.py           # Saari settings (.env se load hoti hain)
├── database.py          # MongoDB — users, stats, analytics, maintenance flag
├── ratelimit.py           # Per-user cooldown
├── utils.py                # Display formatting helpers
├── requirements.txt
├── .env.example
├── Dockerfile / docker-compose.yml / Procfile
```

## ⚠️ Limits

- Telegram Bot API default file-size limit **50MB** hai. Bade files ke liye apna [local Bot API server](https://github.com/tdlib/telegram-bot-api) host karo, phir `MAX_FILE_SIZE_MB` badha do.
- Ek archive me `MAX_FILES_TO_SEND` (default 100) se zyada files hongi to sirf pehli itni hi bhejega.
- Ek user ke queue me `MAX_QUEUE_PER_USER` (default 5) se zyada archives nahi ja sakte.

## 🚀 Hosting

Polling-mode bot hai — kisi bhi VPS, Railway, Render, ya apne PC pe chala sakte ho.
24/7 ke liye Docker (`docker compose up -d`) ya `systemd` service use karo.
