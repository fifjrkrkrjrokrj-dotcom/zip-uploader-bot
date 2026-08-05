"""
i18n.py
-------
Real multi-language support (Hindi / English). Har user ki language DB me
save hoti hai (default: config.DEFAULT_LANGUAGE). t(key, lang, **kwargs)
call karo, wo us language ka translated + formatted string deta hai.

Naya language add karna ho: STRINGS ke har key me ek naya lang-code ka
entry daal do (e.g. "ur" Urdu ke liye) aur LANGUAGES dict me button add karo.
"""

LANGUAGES = {
    "hi": "🇮🇳 हिंदी",
    "en": "🇬🇧 English",
}

STRINGS: dict[str, dict[str, str]] = {
    "welcome": {
        "hi": "👋 <b>नमस्ते,</b> {name}\n\n"
              "📦 मुझे zip / rar / 7z / tar file भेजो।\n"
              "⚡️ मैं अंदर की सारी files निकाल कर भेज दूँगा।\n\n"
              "👇 नीचे से option चुनो।",
        "en": "👋 <b>Hello,</b> {name}\n\n"
              "📦 Send me a zip / rar / 7z / tar file.\n"
              "⚡️ I'll extract everything inside and send it to you.\n\n"
              "👇 Choose an option below.",
    },
    "help": {
        "hi": "▸ कोई भी archive file (.zip .rar .7z .tar) भेजो\n"
              "▸ extract karne se pehle main files ki preview dikhaunga\n"
              "▸ preview me 'files' ya 'zip' format choose kar sakte ho\n"
              "▸ ek se zyada archives bhejo to sab queue me process honge\n\n"
              "<b>commands</b>\n"
              "  <code>/start</code> — main menu\n"
              "  <code>/help</code> — ye help message\n"
              "  <code>/stats</code> — bot usage stats\n"
              "  <code>/history</code> — aapki extraction history\n"
              "  <code>/cancel</code> — chal rahi/pending job cancel\n\n"
              "📏 <b>max size:</b> {size} MB\n"
              "🗂 <b>formats:</b> {fmts}\n"
              "🔐 <b>password-protected:</b> bot khud maang lega",
        "en": "▸ Send any archive file (.zip .rar .7z .tar)\n"
              "▸ I'll show a preview of its contents before extracting\n"
              "▸ In the preview pick 'files' or 'zip' delivery\n"
              "▸ Send several archives — they'll all queue up\n\n"
              "<b>commands</b>\n"
              "  <code>/start</code> — main menu\n"
              "  <code>/help</code> — this help message\n"
              "  <code>/stats</code> — bot usage stats\n"
              "  <code>/history</code> — your extraction history\n"
              "  <code>/cancel</code> — cancel current/pending job\n\n"
              "📏 <b>max size:</b> {size} MB\n"
              "🗂 <b>formats:</b> {fmts}\n"
              "🔐 <b>password-protected:</b> the bot will ask for it",
    },
    "cancel_done": {"hi": "🛑 cancel ho gaya.", "en": "🛑 Cancelled."},
    "cancel_none": {"hi": "ℹ️ koi active job nahi hai.", "en": "ℹ️ No active job right now."},
    "queue_full": {
        "hi": "⚠️ queue full hai, pehle purani archives process hone do.",
        "en": "⚠️ Your queue is full — let earlier archives finish first.",
    },
    "queue_position": {
        "hi": "⏳ {name} queue me hai (position {pos}).",
        "en": "⏳ {name} is queued (position {pos}).",
    },
    "unsupported_format": {
        "hi": "⚠️ ye supported archive nahi hai.\nsupported formats: {fmts}",
        "en": "⚠️ This isn't a supported archive.\nSupported formats: {fmts}",
    },
    "file_too_large": {
        "hi": "⚠️ file bahut badi hai ({size}). max limit: {limit} MB.",
        "en": "⚠️ File is too large ({size}). Max limit: {limit} MB.",
    },
    "join_channel_first": {
        "hi": "🔔 bot use karne ke liye pehle channel join karo:",
        "en": "🔔 Please join our channel before using the bot:",
    },
    "maintenance": {
        "hi": "🛠 bot abhi maintenance mode me hai, thodi der baad try karo.",
        "en": "🛠 The bot is in maintenance mode right now — please try again later.",
    },
    "rate_limited": {
        "hi": "⏳ itni jaldi nahi — thoda ruko: {secs}s",
        "en": "⏳ Slow down a bit — wait {secs}s",
    },
    "downloading": {
        "hi": "⬇️ <b>download ho raha hai</b> {name}\n({size})\n{bar}",
        "en": "⬇️ <b>Downloading</b> {name}\n({size})\n{bar}",
    },
    "download_failed": {"hi": "❌ download fail ho gaya: {err}", "en": "❌ Download failed: {err}"},
    "scanning": {
        "hi": "🛡 <b>virus scan ho raha hai...</b> {name}",
        "en": "🛡 <b>Scanning for viruses...</b> {name}",
    },
    "scan_infected": {
        "hi": "🚫 <b>malware detect hua!</b> ye file safe nahi hai, extraction cancel kar diya.\n<code>{detail}</code>",
        "en": "🚫 <b>Malware detected!</b> This file isn't safe — extraction cancelled.\n<code>{detail}</code>",
    },
    "scan_unavailable_blocked": {
        "hi": "❌ virus scanner (ClamAV) available nahi hai, safety ke liye upload reject kar diya. admin se contact karo.",
        "en": "❌ Virus scanner (ClamAV) is unavailable — upload rejected for safety. Please contact the admin.",
    },
    "listing": {"hi": "🔍 <b>archive padha ja raha hai...</b> {name}", "en": "🔍 <b>Reading archive contents...</b> {name}"},
    "cache_hit": {
        "hi": "⚡️ <b>{name}</b> pehle bhi process ho chuki hai — turant preview ready!",
        "en": "⚡️ <b>{name}</b> was already processed before — instant preview!",
    },
    "password_needed": {
        "hi": "🔐 ye archive password-protected hai.\nneeche reply karke password bhejo.",
        "en": "🔐 This archive is password-protected.\nReply below with the password.",
    },
    "password_ask": {"hi": "🔑 password bhejo:", "en": "🔑 Send the password:"},
    "password_timeout": {
        "hi": "⌛ password timeout ho gaya. dubara file bhejo.",
        "en": "⌛ Password timed out. Please send the file again.",
    },
    "wrong_password": {
        "hi": "❌ galat password. dubara /cancel karke file bhejo.",
        "en": "❌ Wrong password. Use /cancel and send the file again.",
    },
    "zip_bomb": {"hi": "❌ zip-bomb protection: {err}", "en": "❌ Zip-bomb protection: {err}"},
    "unsafe_path": {
        "hi": "❌ is archive me unsafe/suspicious file paths hain — process nahi kiya.",
        "en": "❌ This archive has unsafe/suspicious file paths — not processed.",
    },
    "unsupported_archive": {"hi": "❌ {err}", "en": "❌ {err}"},
    "list_failed": {
        "hi": "❌ archive padhne me error: {err}",
        "en": "❌ Error reading the archive: {err}",
    },
    "empty_archive": {
        "hi": "📭 archive khaali hai — koi file nahi mili.",
        "en": "📭 The archive is empty — no files found.",
    },
    "preview_ready": {
        "hi": "🔍 <b>preview</b> — {total} file(s) mili ({size})\n\n"
              "<code>{names}</code>{more}{risky}\n\n"
              "kaise extract karke bhejun?",
        "en": "🔍 <b>Preview</b> — found {total} file(s) ({size})\n\n"
              "<code>{names}</code>{more}{risky}\n\n"
              "How should I extract & send it?",
    },
    "preview_more": {"hi": "\n  … aur {n} files", "en": "\n  … and {n} more files"},
    "preview_risky": {
        "hi": "\n\n⚠️ {n} risky file(s) ({exts}) safety ki wajah se skip ho jaayengi.",
        "en": "\n\n⚠️ {n} risky file(s) ({exts}) will be skipped for safety.",
    },
    "job_expired": {"hi": "⚠️ ye job expire ho chuki hai.", "en": "⚠️ This job has expired."},
    "extracting": {"hi": "📦 <b>extracting</b> {name} ...", "en": "📦 <b>Extracting</b> {name} ..."},
    "extraction_failed": {
        "hi": "❌ extraction fail ho gayi: {err}",
        "en": "❌ Extraction failed: {err}",
    },
    "zipping": {"hi": "🗜 <b>zip ban raha hoon...</b>", "en": "🗜 <b>Building the zip...</b>"},
    "zip_error": {"hi": "❌ zip banane/bhejne me error: {err}", "en": "❌ Error building/sending the zip: {err}"},
    "done_zip": {"hi": "🎉 <b>done!</b> zip bhej diya.", "en": "🎉 <b>Done!</b> Sent as a zip."},
    "sending_files": {
        "hi": "📤 <b>files bheji ja rahi hain...</b>\n{bar}  ({sent}/{total})",
        "en": "📤 <b>Sending files...</b>\n{bar}  ({sent}/{total})",
    },
    "done_files": {"hi": "🎉 <b>done!</b> {sent}/{total} file(s) bheji gayi.", "en": "🎉 <b>Done!</b> Sent {sent}/{total} file(s)."},
    "truncated_note": {
        "hi": "\n⚠️ archive me total {total} files thi, limit ({limit}) ki wajah se sirf kuch hi bheji gayi.",
        "en": "\n⚠️ The archive had {total} files in total — only some were sent due to the ({limit}) limit.",
    },
    "skipped_blacklist_note": {
        "hi": "\n🚫 {n} risky file(s) safety ki wajah se nahi bheji gayi.",
        "en": "\n🚫 {n} risky file(s) were not sent for safety reasons.",
    },
    "unsupported_message": {
        "hi": "📦 mujhe ek archive file (.zip .rar .7z .tar) bhejo,\nmain uski saari files extract karke bhej dunga.\n\ncommands ke liye /help likho.",
        "en": "📦 Send me an archive file (.zip .rar .7z .tar),\nI'll extract and send everything inside it.\n\nType /help for commands.",
    },
    "language_set": {"hi": "✅ language set ho gayi: <b>हिंदी</b>", "en": "✅ Language set to: <b>English</b>"},
    "choose_language": {"hi": "🌐 <b>apni language chuno:</b>", "en": "🌐 <b>Choose your language:</b>"},
    "stats": {
        "hi": "👥 <b>total users:</b> {users}\n📦 <b>total extractions:</b> {ext}",
        "en": "👥 <b>Total users:</b> {users}\n📦 <b>Total extractions:</b> {ext}",
    },
    "history_empty": {"hi": "📭 abhi tak koi extraction history nahi hai.", "en": "📭 No extraction history yet."},
    "history_header": {"hi": "🗓 <b>aapki history (last {n})</b>", "en": "🗓 <b>Your history (last {n})</b>"},
    "fsub_joined_alert": {"hi": "shukriya! ab archive bhej do.", "en": "Thanks! Now send the archive."},
    "fsub_not_joined_alert": {"hi": "abhi bhi channel join nahi kiya.", "en": "You haven't joined the channel yet."},
    "fsub_verified": {
        "hi": "✅ verified! ab apni archive file bhejo.",
        "en": "✅ Verified! Now send your archive file.",
    },
}


BUTTONS: dict[str, dict[str, str]] = {
    "add_group": {"hi": "➕ add me to your group", "en": "➕ add me to your group"},
    "support": {"hi": "🆘 support", "en": "🆘 support"},
    "owner": {"hi": "👤 owner", "en": "👤 owner"},
    "updates": {"hi": "📢 updates", "en": "📢 updates"},
    "language": {"hi": "🌐 language", "en": "🌐 language"},
    "help": {"hi": "❓ help and commands", "en": "❓ help and commands"},
    "source": {"hi": "💻 source", "en": "💻 source"},
    "back": {"hi": "⬅️ back", "en": "⬅️ back"},
    "join_channel": {"hi": "🔔 join channel", "en": "🔔 join channel"},
    "joined": {"hi": "✅ i've joined", "en": "✅ i've joined"},
    "send_files": {"hi": "✅ send files", "en": "✅ send files"},
    "send_zip": {"hi": "🗜 send as zip", "en": "🗜 send as zip"},
    "cancel": {"hi": "❌ cancel", "en": "❌ cancel"},
}


def tb(key: str, lang: str = "hi") -> str:
    entry = BUTTONS.get(key, {})
    return entry.get(lang) or entry.get("hi") or key


def t(key: str, lang: str = "hi", **kwargs) -> str:
    """Translated + formatted string. Unknown key/lang -> Hindi -> raw key fallback."""
    entry = STRINGS.get(key)
    if not entry:
        return key
    template = entry.get(lang) or entry.get("hi") or next(iter(entry.values()))
    try:
        return template.format(**kwargs)
    except Exception:
        return template
