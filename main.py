"""
main.py
-------
Professional ZIP/RAR/7Z/TAR Extractor Bot — entry point (Pyrogram/MTProto).

SETUP:
1. pip install -r requirements.txt
2. .env me BOT_TOKEN, API_ID, API_HASH, OWNER_ID, MONGO_URI, waghera daalo
   (API_ID/API_HASH free milte hain https://my.telegram.org se)
3. python main.py

Ye bot Pyrogram (MTProto client) use karta hai, HTTP Bot-API wrapper
(python-telegram-bot) ke bajaye — isse files 2GB tak seedha bheji/receive
ki ja sakti hain, koi local Bot-API server host karne ki zaroorat nahi.

FEATURES: nested archive auto-extraction, real preview-before-extract, real
Hindi/English translations, ClamAV malware scan, file-type blacklist,
Redis-backed rate-limit, /logs command, per-user history, auto MongoDB
backup, admin activity feed, add/remove-admin, "delete all sent files"
panic button, duplicate detection, media broadcast, scheduled broadcast,
VIP/premium tiers, aur web dashboard. Dekho README.md for details.
"""

import asyncio
import html
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pyrogram import Client, filters, idle
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ForceReply,
)
from pyrogram.enums import ChatAction, ParseMode, ChatMemberStatus
from pyrogram.errors import RPCError, UserNotParticipant

import config
import database as db
import admin
import security
import clamav
import notify
import logbuffer
import i18n
import dedup
import state
from ratelimit import is_rate_limited, mark_action
from utils import human_size, progress_bar, to_small_caps as sc, DIVIDER

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logbuffer.attach(level=logging.WARNING)

# ============================================================
#  IN-MEMORY STATE (per-process; queues/pending jobs don't need to
#  survive a restart — DB-backed state like rate-limits/history does)
# ============================================================
CHAT_QUEUES: dict[int, asyncio.Queue] = {}
CHAT_WORKER_RUNNING: set[int] = set()
EXTRACTION_SEMAPHORE = asyncio.Semaphore(config.MAX_CONCURRENT_EXTRACTIONS)
PENDING_PREVIEW: dict[str, dict] = {}       # job_id -> archive info, awaiting extract-choice/cancel
PENDING_PASSWORD: dict[int, dict] = {}      # chat_id -> archive info (awaiting password reply)


# ============================================================
#  A "not a command" filter — Pyrogram has no built-in generic COMMAND filter
# ============================================================
async def _not_command(_, __, message: Message) -> bool:
    return not (message.text and message.text.startswith("/"))


NOT_COMMAND = filters.create(_not_command)


# ============================================================
#  KEYBOARDS
# ============================================================
def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(
                sc(i18n.tb("add_group", lang)),
                url=f"https://t.me/{config.BOT_USERNAME}?startgroup=true",
            )],
            [
                InlineKeyboardButton(sc(i18n.tb("support", lang)), url=config.SUPPORT_CHAT_URL),
                InlineKeyboardButton(sc(i18n.tb("owner", lang)), url=config.OWNER_URL),
            ],
            [
                InlineKeyboardButton(sc(i18n.tb("updates", lang)), url=config.UPDATES_CHANNEL_URL),
                InlineKeyboardButton(sc(i18n.tb("language", lang)), callback_data="menu_language"),
            ],
            [InlineKeyboardButton(sc(i18n.tb("help", lang)), callback_data="menu_help")],
            [InlineKeyboardButton(sc(i18n.tb("source", lang)), url=config.SOURCE_URL)],
        ]
    )


def back_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(sc(i18n.tb("back", lang)), callback_data="menu_home")]])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
                InlineKeyboardButton("🇮🇳 हिंदी", callback_data="lang_hi"),
            ],
            [InlineKeyboardButton(sc(i18n.tb("back", "hi")), callback_data="menu_home")],
        ]
    )


def fsub_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(sc(i18n.tb("join_channel", lang)), url=config.FORCE_SUB_CHANNEL_URL)],
            [InlineKeyboardButton(sc(i18n.tb("joined", lang)), callback_data="fsub_check")],
        ]
    )


def preview_keyboard(job_id: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(sc(i18n.tb("send_files", lang)), callback_data=f"job_send_{job_id}"),
                InlineKeyboardButton(sc(i18n.tb("send_zip", lang)), callback_data=f"job_zip_{job_id}"),
            ],
            [InlineKeyboardButton(sc(i18n.tb("cancel", lang)), callback_data=f"job_cancel_{job_id}")],
        ]
    )


# ============================================================
#  BASIC COMMAND HANDLERS
#  (signature convention: async def handler(client, message))
# ============================================================
async def start_command(client, message: Message):
    user = message.from_user
    await db.add_user(user.id, user.first_name, user.username)
    lang = await db.get_user_lang(user.id)
    await notify.notify_start(client, user)
    await message.reply_text(
        i18n.t("welcome", lang, name=user.first_name),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(lang),
    )


async def help_command(client, message: Message):
    lang = await db.get_user_lang(message.from_user.id)
    tier = await db.get_user_tier(message.from_user.id)
    limit = config.limits_for_tier(tier)["max_file_size_mb"]
    await message.reply_text(
        i18n.t("help", lang, size=limit, fmts=", ".join(config.SUPPORTED_EXTENSIONS)),
        parse_mode=ParseMode.HTML,
    )


async def stats_command(client, message: Message):
    lang = await db.get_user_lang(message.from_user.id)
    total_users = await db.get_user_count()
    total_extractions = await db.get_total_extractions()
    await message.reply_text(
        f"✦  <b>{sc('bot stats')}</b>  ✦\n{DIVIDER}\n\n"
        + i18n.t("stats", lang, users=total_users, ext=total_extractions),
        parse_mode=ParseMode.HTML,
    )


async def history_command(client, message: Message):
    user = message.from_user
    lang = await db.get_user_lang(user.id)
    records = await db.get_user_history(user.id, limit=10)
    if not records:
        await message.reply_text(i18n.t("history_empty", lang))
        return

    lines = []
    for r in records:
        when = r["at"].strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"  • {html.escape(r['file_name'])} — {r['files_count']} files ({human_size(r['size_bytes'])}) — {when}")

    text = i18n.t("history_header", lang, n=len(records)) + "\n\n<code>" + "\n".join(lines) + "</code>"
    await message.reply_text(text, parse_mode=ParseMode.HTML)


async def cancel_command(client, message: Message):
    chat_id = message.chat.id
    lang = await db.get_user_lang(message.from_user.id)
    cleared = False

    if chat_id in PENDING_PASSWORD:
        info = PENDING_PASSWORD.pop(chat_id)
        security.cleanup(info["archive_path"])
        cleared = True

    for jid in list(PENDING_PREVIEW.keys()):
        job = PENDING_PREVIEW[jid]
        if job["chat_id"] == chat_id:
            PENDING_PREVIEW.pop(jid, None)
            if not (job.get("from_cache") or config.CACHE_ENABLED):
                security.cleanup(job["archive_path"], job["extract_dir"])
            elif job.get("archive_path"):
                security.cleanup(job["archive_path"])
            cleared = True

    q = CHAT_QUEUES.get(chat_id)
    if q:
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except asyncio.QueueEmpty:
                break
        cleared = True

    # Admin ke pending multi-step flows (ban/broadcast/etc) bhi clear kar do.
    state.get_user_data(message.from_user.id).clear()

    await message.reply_text(i18n.t("cancel_done", lang) if cleared else i18n.t("cancel_none", lang))


async def broadcast_command(client, message: Message):
    """Sirf admin use kar sakte hain — sabhi users ko text message bhejta hai (batched, flood-safe)."""
    if not admin.is_admin(message.from_user.id):
        return
    args = message.command[1:] if message.command else []
    if not args:
        await message.reply_text("Usage: /broadcast <message>")
        return

    text = " ".join(args)
    user_ids = await db.get_all_user_ids()
    sent, failed = 0, 0
    status = await message.reply_text(f"📣 Broadcasting to {len(user_ids)} users...")

    semaphore = asyncio.Semaphore(20)  # flood-safe concurrency

    async def send_one(uid: int):
        nonlocal sent, failed
        async with semaphore:
            try:
                await client.send_message(chat_id=uid, text=text)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)  # ~20 msgs/sec, Telegram-safe

    await asyncio.gather(*(send_one(uid) for uid in user_ids))
    await status.edit_text(f"✅ Broadcast complete.\nSent: {sent} | Failed: {failed}")


async def schedule_broadcast_command(client, message: Message):
    """
    /schedulebroadcast YYYY-MM-DD HH:MM (UTC) — us message par REPLY karke
    bhejo jise broadcast karna hai (text/photo/document/video, sab chalega).
    """
    if not admin.is_admin(message.from_user.id):
        return
    args = message.command[1:] if message.command else []
    if not args:
        await message.reply_text(
            "Usage: reply to the message you want to broadcast with:\n"
            "/schedulebroadcast YYYY-MM-DD HH:MM  (UTC time)"
        )
        return
    if not message.reply_to_message:
        await message.reply_text("⚠️ Is command ko us message par REPLY karke bhejo jise broadcast karna hai.")
        return
    try:
        run_at = datetime.strptime(" ".join(args), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        await message.reply_text("⚠️ Format galat hai. Use: /schedulebroadcast YYYY-MM-DD HH:MM")
        return
    if run_at <= datetime.now(timezone.utc):
        await message.reply_text("⚠️ Ye time past me hai — future ka time do (UTC).")
        return

    target = message.reply_to_message
    await db.add_scheduled_broadcast(run_at, target.chat.id, target.id)
    await message.reply_text(f"✅ Broadcast schedule ho gaya: {run_at.isoformat()} UTC ke liye.")


async def scheduled_broadcast_loop(client):
    """Har 30s check karta hai ki koi scheduled broadcast due hua ya nahi."""
    while True:
        await asyncio.sleep(30)
        try:
            due = await db.get_due_scheduled_broadcasts(datetime.now(timezone.utc))
            for item in due:
                try:
                    await admin.execute_broadcast_copy(client, item["from_chat_id"], item["message_id"])
                finally:
                    await db.mark_scheduled_broadcast_sent(item["_id"])
        except Exception:
            logger.exception("Scheduled-broadcast loop failed")


# ============================================================
#  MENU / LANGUAGE CALLBACKS
# ============================================================
async def button_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user = callback_query.from_user

    if data.startswith("admin_"):
        return await admin.admin_callback(client, callback_query)
    if data.startswith("job_"):
        return await job_callback(client, callback_query)
    if data == "fsub_check":
        return await fsub_check_callback(client, callback_query)

    await callback_query.answer()
    lang = await db.get_user_lang(user.id)

    if data == "menu_home":
        await callback_query.edit_message_text(
            i18n.t("welcome", lang, name=user.first_name),
            parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(lang),
        )
    elif data == "menu_help":
        tier = await db.get_user_tier(user.id)
        limit = config.limits_for_tier(tier)["max_file_size_mb"]
        await callback_query.edit_message_text(
            i18n.t("help", lang, size=limit, fmts=", ".join(config.SUPPORTED_EXTENSIONS)),
            parse_mode=ParseMode.HTML, reply_markup=back_keyboard(lang),
        )
    elif data == "menu_language":
        await callback_query.edit_message_text(
            i18n.t("choose_language", lang),
            parse_mode=ParseMode.HTML, reply_markup=language_keyboard(),
        )
    elif data in ("lang_en", "lang_hi"):
        new_lang = "en" if data == "lang_en" else "hi"
        await db.set_user_lang(user.id, new_lang)
        await callback_query.edit_message_text(
            i18n.t("language_set", new_lang),
            parse_mode=ParseMode.HTML, reply_markup=back_keyboard(new_lang),
        )


async def fsub_check_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    lang = await db.get_user_lang(user_id)
    if await check_subscribed(client, user_id):
        await callback_query.answer(i18n.t("fsub_joined_alert", lang), show_alert=True)
        await callback_query.edit_message_text(i18n.t("fsub_verified", lang))
    else:
        await callback_query.answer(i18n.t("fsub_not_joined_alert", lang), show_alert=True)


# ============================================================
#  FORCE SUBSCRIBE
# ============================================================
async def check_subscribed(client, user_id: int) -> bool:
    if not config.FORCE_SUB_CHANNEL:
        return True
    try:
        member = await client.get_chat_member(config.FORCE_SUB_CHANNEL, user_id)
        return member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
    except UserNotParticipant:
        return False
    except RPCError:
        return True  # channel misconfigured — fail-open taaki bot block na ho


# ============================================================
#  QUEUE WORKER
# ============================================================
async def enqueue_job(chat_id: int, job: dict, client):
    lang = await db.get_user_lang(job["user"].id)
    tier = await db.get_user_tier(job["user"].id)
    max_queue = config.limits_for_tier(tier)["max_queue"]
    queue = CHAT_QUEUES.setdefault(chat_id, asyncio.Queue())
    if queue.qsize() >= max_queue:
        await client.send_message(chat_id=chat_id, text=i18n.t("queue_full", lang))
        return
    await queue.put(job)
    if queue.qsize() > 1:
        await client.send_message(
            chat_id=chat_id,
            text=i18n.t("queue_position", lang, name=job["file_name"], pos=queue.qsize()),
        )
    if chat_id not in CHAT_WORKER_RUNNING:
        CHAT_WORKER_RUNNING.add(chat_id)
        asyncio.create_task(chat_worker(chat_id, client))


async def chat_worker(chat_id: int, client):
    queue = CHAT_QUEUES[chat_id]
    try:
        while not queue.empty():
            job = await queue.get()
            try:
                async with EXTRACTION_SEMAPHORE:
                    await process_archive_job(job, client)
            except Exception:
                logger.exception("Job processing failed")
            finally:
                queue.task_done()
    finally:
        CHAT_WORKER_RUNNING.discard(chat_id)


# ============================================================
#  ARCHIVE HANDLING (core feature)
# ============================================================
async def handle_document(client, message: Message):
    document = message.document
    if document is None:
        return

    user = message.from_user
    chat_id = message.chat.id
    lang = await db.get_user_lang(user.id)
    user_data = state.get_user_data(user.id)

    # ---- Admin broadcast-content capture (admin panel "📢 broadcast now") ----
    if user_data.get("awaiting_broadcast_message") and admin.is_admin(user.id):
        user_data.pop("awaiting_broadcast_message")
        await admin.execute_broadcast_from_message(client, message)
        return

    if await db.is_banned(user.id):
        return  # silently ignore banned users

    if not admin.is_admin(user.id) and await db.get_maintenance():
        await message.reply_text(i18n.t("maintenance", lang))
        return

    await db.add_user(user.id, user.first_name, user.username)
    await db.log_active_user(user.id)

    tier = await db.get_user_tier(user.id)
    limits = config.limits_for_tier(tier)

    limited, wait_s = is_rate_limited(user.id, limits["rate_limit_seconds"])
    if limited:
        await message.reply_text(i18n.t("rate_limited", lang, secs=wait_s))
        return

    file_name = document.file_name or "archive"
    lower_name = file_name.lower()

    if not lower_name.endswith(config.SUPPORTED_EXTENSIONS):
        await message.reply_text(
            i18n.t("unsupported_format", lang, fmts=", ".join(config.SUPPORTED_EXTENSIONS))
        )
        return

    size_mb = document.file_size / (1024 * 1024)
    if size_mb > limits["max_file_size_mb"]:
        await message.reply_text(
            i18n.t("file_too_large", lang, size=human_size(document.file_size), limit=limits["max_file_size_mb"])
        )
        return

    if not await check_subscribed(client, user.id):
        await message.reply_text(i18n.t("join_channel_first", lang), reply_markup=fsub_keyboard(lang))
        return

    mark_action(user.id, limits["rate_limit_seconds"])
    await notify.notify_forward(client, message, user, "📦 New file received")

    # ---- Duplicate detection — same file pehle process ho chuki ho to cache se serve ----
    cache_hit = await dedup.get_cache_hit(document.file_unique_id)
    if cache_hit:
        status = await message.reply_text(i18n.t("cache_hit", lang, name=file_name))
        await show_preview_from_directory(
            chat_id, user.id, Path(cache_hit["extract_dir"]), file_name, status,
            archive_path=None, file_unique_id=document.file_unique_id, from_cache=True,
        )
        return

    await enqueue_job(
        chat_id,
        {
            "chat_id": chat_id, "user": user, "message": message,
            "file_name": file_name, "file_unique_id": document.file_unique_id,
            "file_size": document.file_size,
        },
        client,
    )


async def process_archive_job(job: dict, client):
    chat_id = job["chat_id"]
    user = job["user"]
    message = job["message"]
    file_name = job["file_name"]
    file_unique_id = job["file_unique_id"]
    file_size = job["file_size"]
    lang = await db.get_user_lang(user.id)

    user_dir = Path(config.DOWNLOAD_DIR) / str(chat_id)
    if config.CACHE_ENABLED:
        extract_dir = dedup.cache_dir_for(file_unique_id)
    else:
        extract_dir = Path(config.EXTRACT_DIR) / str(chat_id) / uuid.uuid4().hex[:8]
    user_dir.mkdir(parents=True, exist_ok=True)
    archive_path = user_dir / f"{uuid.uuid4().hex[:8]}_{file_name}"

    status = await client.send_message(
        chat_id=chat_id,
        text=i18n.t("downloading", lang, name=file_name, size=human_size(file_size), bar=progress_bar(0)),
        parse_mode=ParseMode.HTML,
    )

    try:
        await message.download(file_name=str(archive_path))
    except Exception as e:
        logger.exception("Download failed")
        await status.edit_text(i18n.t("download_failed", lang, err=e))
        security.cleanup(archive_path)
        return

    # ---- Virus / malware scan (ClamAV) — pehle archive scan hota hai ----
    if config.CLAMAV_ENABLED:
        await status.edit_text(i18n.t("scanning", lang, name=file_name), parse_mode=ParseMode.HTML)
        try:
            clean, detail = await clamav.scan_file(archive_path)
            if not clean:
                safe_detail = html.escape(detail[:300])
                await status.edit_text(i18n.t("scan_infected", lang, detail=safe_detail), parse_mode=ParseMode.HTML)
                security.cleanup(archive_path)
                await notify.notify_text(
                    client,
                    f"🚫 <b>Malware detected</b>\n👤 {user.first_name} (<code>{user.id}</code>)\n"
                    f"📦 {html.escape(file_name)}\n<code>{safe_detail}</code>",
                )
                return
        except clamav.ScanUnavailable as e:
            if config.CLAMAV_REQUIRED:
                await status.edit_text(i18n.t("scan_unavailable_blocked", lang))
                security.cleanup(archive_path)
                return
            logger.warning("ClamAV unavailable, continuing without scan (fail-open): %s", e)

    await proceed_to_preview(client, chat_id, user.id, archive_path, extract_dir, file_name, status,
                              password=None, file_unique_id=file_unique_id)


async def proceed_to_preview(client, chat_id: int, user_id: int, archive_path: Path,
                              extract_dir: Path, file_name: str, status, password: str | None = None,
                              file_unique_id: str | None = None):
    """Archive ke contents list karta hai (bina extract kiye) aur preview dikhata hai."""
    lang = await db.get_user_lang(user_id)
    await status.edit_text(i18n.t("listing", lang, name=file_name), parse_mode=ParseMode.HTML)

    try:
        listing = security.list_archive_contents(archive_path, password=password)
    except security.PasswordRequiredError:
        PENDING_PASSWORD[chat_id] = {
            "archive_path": archive_path, "extract_dir": extract_dir,
            "file_name": file_name, "status_message": status,
            "timestamp": time.time(), "user_id": user_id, "file_unique_id": file_unique_id,
        }
        await status.edit_text(i18n.t("password_needed", lang))
        await client.send_message(chat_id=chat_id, text=i18n.t("password_ask", lang), reply_markup=ForceReply(selective=True))
        return
    except security.WrongPasswordError:
        await status.edit_text(i18n.t("wrong_password", lang))
        security.cleanup(archive_path)
        return
    except security.UnsupportedArchiveError as e:
        await status.edit_text(i18n.t("unsupported_archive", lang, err=str(e)))
        security.cleanup(archive_path)
        return
    except Exception as e:
        logger.exception("Listing archive contents failed")
        await status.edit_text(i18n.t("list_failed", lang, err=str(e)))
        security.cleanup(archive_path)
        return

    if not listing:
        await status.edit_text(i18n.t("empty_archive", lang))
        security.cleanup(archive_path)
        return

    total = len(listing)
    total_size = sum(sz for _, sz in listing)
    risky_names = [n for n, _ in listing if Path(n).suffix.lower() in config.BLACKLIST_EXTENSIONS]

    job_id = uuid.uuid4().hex[:10]
    PENDING_PREVIEW[job_id] = {
        "chat_id": chat_id, "user_id": user_id, "archive_path": archive_path,
        "extract_dir": extract_dir, "file_name": file_name, "password": password,
        "file_unique_id": file_unique_id, "from_cache": False,
    }

    preview_names = "\n".join(f"  • {html.escape(n)}" for n, _ in listing[:10])
    more_note = i18n.t("preview_more", lang, n=total - 10) if total > 10 else ""
    risky_note = ""
    if risky_names:
        exts = ", ".join(sorted({Path(n).suffix.lower() for n in risky_names}))
        risky_note = i18n.t("preview_risky", lang, n=len(risky_names), exts=exts)

    await status.edit_text(
        i18n.t(
            "preview_ready", lang, total=total, size=human_size(total_size),
            names=preview_names, more=more_note, risky=risky_note,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=preview_keyboard(job_id, lang),
    )


async def show_preview_from_directory(chat_id: int, user_id: int, extract_dir: Path, file_name: str, status,
                                       archive_path: Path | None, file_unique_id: str | None, from_cache: bool):
    """
    Cache-hit path: extract_dir me pehle se hi extracted files maujood hain
    (kisi purani job se), isliye seedha directory scan karke preview dikhate
    hain — download/scan/extract kuch nahi karna padta.
    """
    lang = await db.get_user_lang(user_id)
    all_files = security.collect_files(extract_dir)
    if not all_files:
        await status.edit_text(i18n.t("empty_archive", lang))
        return

    _allowed, blocked = security.filter_blacklist(all_files)
    total = len(all_files)
    total_size = sum(f.stat().st_size for f in all_files)

    job_id = uuid.uuid4().hex[:10]
    PENDING_PREVIEW[job_id] = {
        "chat_id": chat_id, "user_id": user_id, "archive_path": archive_path,
        "extract_dir": extract_dir, "file_name": file_name, "password": None,
        "file_unique_id": file_unique_id, "from_cache": from_cache,
    }

    preview_names = "\n".join(f"  • {html.escape(str(f.relative_to(extract_dir)))}" for f in all_files[:10])
    more_note = i18n.t("preview_more", lang, n=total - 10) if total > 10 else ""
    risky_note = ""
    if blocked:
        exts = ", ".join(sorted({f.suffix.lower() for f in blocked}))
        risky_note = i18n.t("preview_risky", lang, n=len(blocked), exts=exts)

    await status.edit_text(
        i18n.t(
            "preview_ready", lang, total=total, size=human_size(total_size),
            names=preview_names, more=more_note, risky=risky_note,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=preview_keyboard(job_id, lang),
    )


# ============================================================
#  PASSWORD REPLY / GENERIC TEXT HANDLER
# ============================================================
async def handle_text(client, message: Message):
    chat_id = message.chat.id
    user = message.from_user

    if await admin.handle_admin_text_input(client, message):
        return

    pending = PENDING_PASSWORD.get(chat_id)
    if pending:
        lang = await db.get_user_lang(pending["user_id"])
        if time.time() - pending["timestamp"] > config.PASSWORD_TIMEOUT_SECONDS:
            PENDING_PASSWORD.pop(chat_id, None)
            security.cleanup(pending["archive_path"])
            await message.reply_text(i18n.t("password_timeout", lang))
            return

        password = (message.text or "").strip()
        PENDING_PASSWORD.pop(chat_id)
        try:
            await message.delete()  # privacy: password message hata do
        except Exception:
            pass
        await proceed_to_preview(
            client, chat_id, pending["user_id"], pending["archive_path"],
            pending["extract_dir"], pending["file_name"], pending["status_message"],
            password=password, file_unique_id=pending.get("file_unique_id"),
        )
        return

    await notify.notify_forward(client, message, user, "💬 New message")
    await handle_unsupported_message(client, message)


async def handle_unsupported_message(client, message: Message):
    lang = await db.get_user_lang(message.from_user.id)
    await message.reply_text(i18n.t("unsupported_message", lang))


# ============================================================
#  PREVIEW → EXTRACT → SEND FILES / SEND ZIP / CANCEL
# ============================================================
async def job_callback(client, callback_query: CallbackQuery):
    await callback_query.answer()
    data = callback_query.data

    # data format: job_send_<id> / job_zip_<id> / job_cancel_<id>
    parts = data.split("_", 2)
    action, job_id = parts[1], parts[2]

    job = PENDING_PREVIEW.pop(job_id, None)
    if not job:
        lang = await db.get_user_lang(callback_query.from_user.id)
        await callback_query.edit_message_text(i18n.t("job_expired", lang))
        return

    chat_id = job["chat_id"]
    user_id = job["user_id"]
    archive_path = job["archive_path"]
    extract_dir = job["extract_dir"]
    file_name = job["file_name"]
    password = job["password"]
    file_unique_id = job.get("file_unique_id")
    from_cache = job.get("from_cache", False)
    lang = await db.get_user_lang(user_id)

    if action == "cancel":
        if not from_cache:
            security.cleanup(archive_path, extract_dir)
        await callback_query.edit_message_text(i18n.t("cancel_done", lang))
        return

    if from_cache:
        # Files already extracted (dedup cache) — koi extraction/nested-scan zaroori nahi.
        pass
    else:
        # Double-check: ho sakta hai isi beech me koi doosra job isi file_unique_id
        # ko already cache me daal chuka ho — to hum dobara extract na karke wahi use karein.
        fresh_hit = await dedup.get_cache_hit(file_unique_id) if (config.CACHE_ENABLED and file_unique_id) else None
        if fresh_hit and Path(fresh_hit["extract_dir"]) != extract_dir:
            security.cleanup(archive_path, extract_dir)
            archive_path = None
            extract_dir = Path(fresh_hit["extract_dir"])
            from_cache = True

    if not from_cache:
        # ---- Extraction happens here, only AFTER the user has seen the preview ----
        await callback_query.edit_message_text(i18n.t("extracting", lang, name=file_name), parse_mode=ParseMode.HTML)
        try:
            security.extract_archive(archive_path, extract_dir, password=password)
        except security.ArchiveTooLargeError as e:
            await callback_query.edit_message_text(i18n.t("zip_bomb", lang, err=str(e)))
            security.cleanup(archive_path, extract_dir)
            return
        except security.UnsafePathError:
            await callback_query.edit_message_text(i18n.t("unsafe_path", lang))
            security.cleanup(archive_path, extract_dir)
            return
        except (security.PasswordRequiredError, security.WrongPasswordError):
            await callback_query.edit_message_text(i18n.t("wrong_password", lang))
            security.cleanup(archive_path, extract_dir)
            return
        except Exception as e:
            logger.exception("Extraction failed")
            await callback_query.edit_message_text(i18n.t("extraction_failed", lang, err=str(e)))
            security.cleanup(archive_path, extract_dir)
            return

        security.cleanup(archive_path)  # archive ab nahi chahiye

        # ---- Nested archive auto-extraction (zip ke andar zip) ----
        try:
            nested_count = security.auto_extract_nested(extract_dir)
            if nested_count:
                logger.info("Auto-extracted %d nested archive(s) for chat %s", nested_count, chat_id)
        except Exception:
            logger.exception("Nested auto-extraction crashed, continuing with top-level files only")

        # ---- Duplicate-detection cache: save pointer so next time same file skips all of this ----
        if config.CACHE_ENABLED and file_unique_id:
            await dedup.store_cache(file_unique_id, extract_dir, file_name)

    all_files = security.collect_files(extract_dir)
    if not all_files:
        await callback_query.edit_message_text(i18n.t("empty_archive", lang))
        if not (from_cache or config.CACHE_ENABLED):
            security.cleanup(extract_dir)
        return

    allowed_files, blocked_files = security.filter_blacklist(all_files)

    # ---- Optional: scan extracted files individually (skip if served from cache — already scanned) ----
    if config.CLAMAV_ENABLED and config.CLAMAV_SCAN_EXTRACTED and not from_cache:
        to_scan = allowed_files[: config.MAX_FILES_TO_SEND]
        rest = allowed_files[config.MAX_FILES_TO_SEND:]
        clean_files = []
        for f in to_scan:
            try:
                clean, _detail = await clamav.scan_file(f)
                (clean_files if clean else blocked_files).append(f)
            except clamav.ScanUnavailable:
                clean_files.append(f)  # fail-open per-file
        allowed_files = clean_files + rest

    total = len(all_files)
    truncated = len(allowed_files) > config.MAX_FILES_TO_SEND
    files_to_send = allowed_files[: config.MAX_FILES_TO_SEND]
    total_size = sum(f.stat().st_size for f in files_to_send) if files_to_send else 0

    if not files_to_send:
        msg = i18n.t("empty_archive", lang)
        if blocked_files:
            msg += i18n.t("skipped_blacklist_note", lang, n=len(blocked_files))
        await callback_query.edit_message_text(msg)
        if not (from_cache or config.CACHE_ENABLED):
            security.cleanup(extract_dir)
        return

    if action == "zip":
        await callback_query.edit_message_text(i18n.t("zipping", lang), parse_mode=ParseMode.HTML)
        zip_path = Path(config.REZIP_DIR) / str(chat_id) / f"{job_id}.zip"
        try:
            security.rezip_files(files_to_send, extract_dir, zip_path)
            await client.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
            sent_msg = await client.send_document(
                chat_id=chat_id, document=str(zip_path), file_name=f"extracted_{job_id}.zip"
            )
            await db.add_sent_message(chat_id, sent_msg.id, kind="zip")
            await db.increment_extractions(files_sent=len(files_to_send))
            await db.add_history(user_id, file_name, len(files_to_send), total_size, "zip")

            final_msg = i18n.t("done_zip", lang)
            if blocked_files:
                final_msg += i18n.t("skipped_blacklist_note", lang, n=len(blocked_files))
            await callback_query.edit_message_text(final_msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.exception("Rezip/send failed")
            await callback_query.edit_message_text(i18n.t("zip_error", lang, err=str(e)))
        finally:
            security.cleanup(zip_path)  # zip hamesha temp hai — extract_dir cache hone par preserve rehta hai
            if not (from_cache or config.CACHE_ENABLED):
                security.cleanup(extract_dir)
        return

    # action == "send" -> individual files
    sent_count = 0
    last_edit = 0.0
    for file_path in files_to_send:
        try:
            await client.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
            sent_msg = await client.send_document(
                chat_id=chat_id, document=str(file_path), file_name=file_path.name,
                caption=str(file_path.relative_to(extract_dir)),
            )
            await db.add_sent_message(chat_id, sent_msg.id, kind="document")
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send {file_path}: {e}")

        now = time.time()
        if now - last_edit > 1.5 or sent_count == len(files_to_send):
            pct = (sent_count / len(files_to_send)) * 100
            try:
                await callback_query.edit_message_text(
                    i18n.t("sending_files", lang, bar=progress_bar(pct), sent=sent_count, total=len(files_to_send)),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            last_edit = now

    await db.increment_extractions(files_sent=sent_count)
    await db.add_history(user_id, file_name, sent_count, total_size, "files")

    final_msg = i18n.t("done_files", lang, sent=sent_count, total=len(files_to_send))
    if truncated:
        final_msg += i18n.t("truncated_note", lang, total=total, limit=config.MAX_FILES_TO_SEND)
    if blocked_files:
        final_msg += i18n.t("skipped_blacklist_note", lang, n=len(blocked_files))
    await callback_query.edit_message_text(final_msg, parse_mode=ParseMode.HTML)
    if not (from_cache or config.CACHE_ENABLED):
        security.cleanup(extract_dir)


# ============================================================
#  MAIN
# ============================================================
def _build_client() -> Client:
    return Client(
        "zipbot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
    )


app = _build_client()


def _register_handlers(client: Client):
    client.add_handler(MessageHandler(start_command, filters.command("start")))
    client.add_handler(MessageHandler(help_command, filters.command("help")))
    client.add_handler(MessageHandler(stats_command, filters.command("stats")))
    client.add_handler(MessageHandler(history_command, filters.command("history")))
    client.add_handler(MessageHandler(cancel_command, filters.command("cancel")))
    client.add_handler(MessageHandler(broadcast_command, filters.command("broadcast")))
    client.add_handler(MessageHandler(schedule_broadcast_command, filters.command("schedulebroadcast")))
    client.add_handler(MessageHandler(admin.admin_command, filters.command("admin")))
    client.add_handler(MessageHandler(admin.logs_command, filters.command("logs")))
    client.add_handler(CallbackQueryHandler(button_callback))
    client.add_handler(MessageHandler(handle_document, filters.document))
    client.add_handler(
        MessageHandler(handle_text, (filters.text & NOT_COMMAND) | filters.photo | filters.video)
    )


async def _startup(client: Client):
    ok, err = await db.check_connection()
    if not ok:
        logger.error("MongoDB connection failed: %s", err)
        raise SystemExit(f"MongoDB se connect nahi ho paya: {err}")
    await db.init_db()
    await admin.load_extra_admins()
    logger.info("MongoDB connected and initialized.")

    import backup  # local imports to dodge any accidental circular import at load time
    import dashboard

    asyncio.create_task(backup.backup_scheduler(client))
    asyncio.create_task(dedup.cache_cleanup_scheduler())
    asyncio.create_task(scheduled_broadcast_loop(client))
    asyncio.create_task(dashboard.run_dashboard())


async def _async_main():
    await app.start()
    await _startup(app)
    me = await app.get_me()
    logger.info("Bot started as @%s (Pyrogram/MTProto client).", me.username)
    await idle()
    await app.stop()


def main():
    if config.BOT_TOKEN.startswith("1234567890:"):
        raise SystemExit("config.py / .env me apna asli BOT_TOKEN daalo, phir bot chalao.")
    if config.API_ID == 12345:
        raise SystemExit("config.py / .env me apna asli API_ID/API_HASH daalo (my.telegram.org se lo).")

    _register_handlers(app)
    app.run(_async_main())


if __name__ == "__main__":
    main()
