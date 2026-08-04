"""
main.py
-------
Professional ZIP/RAR/7Z/TAR Extractor Bot — entry point.

SETUP:
1. pip install -r requirements.txt
2. .env (ya config.py / env vars) me BOT_TOKEN, OWNER_ID, MONGO_URI, waghera daalo
3. python main.py
"""

import asyncio
import logging
import time
import uuid
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ForceReply,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.error import TelegramError

import config
import database as db
import admin
import security
from ratelimit import is_rate_limited, mark_action
from utils import human_size, progress_bar, to_small_caps as sc, DIVIDER

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
#  IN-MEMORY STATE (single-instance polling bot)
# ============================================================
CHAT_QUEUES: dict[int, asyncio.Queue] = {}
CHAT_WORKER_RUNNING: set[int] = set()
EXTRACTION_SEMAPHORE = asyncio.Semaphore(config.MAX_CONCURRENT_EXTRACTIONS)
PENDING_JOBS: dict[str, dict] = {}          # job_id -> extracted-files info (awaiting send/zip/cancel)
PENDING_PASSWORD: dict[int, dict] = {}      # chat_id -> archive info (awaiting password reply)


# ============================================================
#  KEYBOARDS
# ============================================================
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(
                sc("➕ add me to your group"),
                url=f"https://t.me/{config.BOT_USERNAME}?startgroup=true",
                style="success",
            )],
            [
                InlineKeyboardButton(sc("🆘 support"), url=config.SUPPORT_CHAT_URL, style="primary"),
                InlineKeyboardButton(sc("👤 owner"), url=config.OWNER_URL, style="primary"),
            ],
            [
                InlineKeyboardButton(sc("📢 updates"), url=config.UPDATES_CHANNEL_URL, style="primary"),
                InlineKeyboardButton(sc("🌐 language"), callback_data="menu_language", style="primary"),
            ],
            [InlineKeyboardButton(sc("❓ help and commands"), callback_data="menu_help", style="primary")],
            [InlineKeyboardButton(sc("💻 source"), url=config.SOURCE_URL, style="primary")],
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ back"), callback_data="menu_home")]])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇬🇧 English", callback_data="lang_en", style="primary"),
                InlineKeyboardButton("🇮🇳 हिंदी", callback_data="lang_hi", style="primary"),
            ],
            [InlineKeyboardButton(sc("⬅️ back"), callback_data="menu_home")],
        ]
    )


def fsub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(sc("🔔 join channel"), url=config.FORCE_SUB_CHANNEL_URL, style="primary")],
            [InlineKeyboardButton(sc("✅ i've joined"), callback_data="fsub_check", style="success")],
        ]
    )


def preview_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(sc("✅ send files"), callback_data=f"job_send_{job_id}", style="success"),
                InlineKeyboardButton(sc("🗜 send as zip"), callback_data=f"job_zip_{job_id}", style="primary"),
            ],
            [InlineKeyboardButton(sc("❌ cancel"), callback_data=f"job_cancel_{job_id}", style="danger")],
        ]
    )


# ============================================================
#  TEXT TEMPLATES
# ============================================================
WELCOME_TEXT = (
    "✦  <b>{title}</b>  ✦\n"
    f"{DIVIDER}\n\n"
    "👋 <b>{greet}</b> {name}\n\n"
    "📦 {desc1}\n"
    "⚡️ {desc2}\n\n"
    f"{DIVIDER}\n"
    "👇 {footer}"
).format(
    title=sc("archive extractor bot"),
    greet=sc("namaste,"),
    name="{name}",
    desc1=sc("mujhe zip / rar / 7z / tar file bhejo"),
    desc2=sc("main andar ki saari files nikal ke bhej dunga"),
    footer=sc("neeche se option chuno"),
)

HELP_TEXT = (
    "✦  <b>{title}</b>  ✦\n"
    f"{DIVIDER}\n\n"
    "▸ {line1}\n"
    "▸ {line2}\n"
    "▸ {line3}\n"
    "▸ {line4}\n\n"
    "<b>{cmd_title}</b>\n"
    "  <code>/start</code>  —  {c1}\n"
    "  <code>/help</code>  —  {c2}\n"
    "  <code>/stats</code>  —  {c3}\n"
    "  <code>/cancel</code>  —  {c4}\n\n"
    f"{DIVIDER}\n"
    "📏 <b>{size_label}</b> {size}\n"
    "🗂 <b>{fmt_label}</b> {fmts}\n"
    "🔐 <b>{pwd_label}</b> {pwd_desc}"
).format(
    title=sc("help & commands"),
    line1=sc("koi bhi archive file (.zip .rar .7z .tar) bhejo"),
    line2=sc("main use extract karke andar ki saari files bhej dunga"),
    line3=sc("extraction ke baad 'files' ya 'zip' format choose kar sakte ho"),
    line4=sc("ek se zyada archives bhejo to sab queue me process honge"),
    cmd_title=sc("commands"),
    c1=sc("main menu kholta hai"),
    c2=sc("ye help message dikhata hai"),
    c3=sc("bot ke usage stats dikhata hai"),
    c4=sc("chal rahi ya pending job cancel karta hai"),
    size_label=sc("max size:"),
    size=f"{config.MAX_FILE_SIZE_MB} MB",
    fmt_label=sc("formats:"),
    fmts=", ".join(config.SUPPORTED_EXTENSIONS),
    pwd_label=sc("password-protected:"),
    pwd_desc=sc("bot khud password maang lega"),
)


# ============================================================
#  BASIC COMMAND HANDLERS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.first_name, user.username)
    await update.message.reply_text(
        WELCOME_TEXT.format(name=user.first_name),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = await db.get_user_count()
    total_extractions = await db.get_total_extractions()
    await update.message.reply_text(
        f"✦  <b>{sc('bot stats')}</b>  ✦\n{DIVIDER}\n\n"
        f"👥 <b>{sc('total users:')}</b> {total_users}\n"
        f"📦 <b>{sc('total extractions:')}</b> {total_extractions}",
        parse_mode=ParseMode.HTML,
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cleared = False

    if chat_id in PENDING_PASSWORD:
        info = PENDING_PASSWORD.pop(chat_id)
        security.cleanup(info["archive_path"])
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

    await update.message.reply_text(
        f"🛑 {sc('cancel ho gaya.')}" if cleared else f"ℹ️ {sc('koi active job nahi hai.')}"
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sirf admin use kar sakte hain — sabhi users ko message bhejta hai (batched, flood-safe)."""
    if not admin.is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    text = " ".join(context.args)
    user_ids = await db.get_all_user_ids()
    sent, failed = 0, 0
    status = await update.message.reply_text(f"📣 Broadcasting to {len(user_ids)} users...")

    semaphore = asyncio.Semaphore(20)  # flood-safe concurrency

    async def send_one(uid: int):
        nonlocal sent, failed
        async with semaphore:
            try:
                await context.bot.send_message(chat_id=uid, text=text)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)  # ~20 msgs/sec, Telegram-safe

    await asyncio.gather(*(send_one(uid) for uid in user_ids))
    await status.edit_text(f"✅ Broadcast complete.\nSent: {sent} | Failed: {failed}")


# ============================================================
#  MENU / LANGUAGE / ADMIN CALLBACKS
# ============================================================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user

    if data.startswith("admin_"):
        return await admin.admin_callback(update, context)
    if data.startswith("job_"):
        return await job_callback(update, context)
    if data == "fsub_check":
        return await fsub_check_callback(update, context)

    await query.answer()
    if data == "menu_home":
        await query.edit_message_text(
            WELCOME_TEXT.format(name=user.first_name),
            parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(),
        )
    elif data == "menu_help":
        await query.edit_message_text(HELP_TEXT, parse_mode=ParseMode.HTML, reply_markup=back_keyboard())
    elif data == "menu_language":
        await query.edit_message_text(
            f"🌐 <b>{sc('apni language chuno:')}</b>",
            parse_mode=ParseMode.HTML, reply_markup=language_keyboard(),
        )
    elif data in ("lang_en", "lang_hi"):
        chosen = "English" if data == "lang_en" else "हिंदी"
        await query.edit_message_text(
            f"✅ {sc('language set to')} <b>{chosen}</b>",
            parse_mode=ParseMode.HTML, reply_markup=back_keyboard(),
        )


async def fsub_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if await check_subscribed(context.bot, user_id):
        await query.answer(sc("shukriya! ab archive bhej do."), show_alert=True)
        await query.edit_message_text(f"✅ {sc('verified! ab apni archive file bhejo.')}")
    else:
        await query.answer(sc("abhi bhi channel join nahi kiya."), show_alert=True)


# ============================================================
#  FORCE SUBSCRIBE
# ============================================================
async def check_subscribed(bot, user_id: int) -> bool:
    if not config.FORCE_SUB_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(config.FORCE_SUB_CHANNEL, user_id)
        return member.status not in ("left", "kicked")
    except TelegramError:
        return True  # channel misconfigured — fail-open taaki bot block na ho


# ============================================================
#  QUEUE WORKER
# ============================================================
async def enqueue_job(chat_id: int, job: dict, bot):
    queue = CHAT_QUEUES.setdefault(chat_id, asyncio.Queue())
    if queue.qsize() >= config.MAX_QUEUE_PER_USER:
        await bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {sc('queue full hai, pehle purani archives process hone do.')}",
        )
        return
    await queue.put(job)
    if queue.qsize() > 1:
        await bot.send_message(
            chat_id=chat_id,
            text=f"⏳ {job['file_name']} {sc('queue me hai (position')} {queue.qsize()}{sc(').')}",
        )
    if chat_id not in CHAT_WORKER_RUNNING:
        CHAT_WORKER_RUNNING.add(chat_id)
        asyncio.create_task(chat_worker(chat_id, bot))


async def chat_worker(chat_id: int, bot):
    queue = CHAT_QUEUES[chat_id]
    try:
        while not queue.empty():
            job = await queue.get()
            try:
                async with EXTRACTION_SEMAPHORE:
                    await process_archive_job(job, bot)
            except Exception:
                logger.exception("Job processing failed")
            finally:
                queue.task_done()
    finally:
        CHAT_WORKER_RUNNING.discard(chat_id)


# ============================================================
#  ARCHIVE HANDLING (core feature)
# ============================================================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if document is None:
        return

    user = update.effective_user
    chat_id = update.effective_chat.id

    if await db.is_banned(user.id):
        return  # silently ignore banned users

    if not admin.is_admin(user.id) and await db.get_maintenance():
        await update.message.reply_text(f"🛠 {sc('bot abhi maintenance mode me hai, thodi der baad try karo.')}")
        return

    await db.add_user(user.id, user.first_name, user.username)
    await db.log_active_user(user.id)

    limited, wait_s = is_rate_limited(user.id)
    if limited:
        await update.message.reply_text(f"⏳ {sc('itni jaldi nahi — thoda ruko:')} {wait_s}s")
        return

    file_name = document.file_name or "archive"
    lower_name = file_name.lower()

    if not lower_name.endswith(config.SUPPORTED_EXTENSIONS):
        await update.message.reply_text(
            f"⚠️ {sc('ye supported archive nahi hai.')}\n"
            f"{sc('supported formats:')} {', '.join(config.SUPPORTED_EXTENSIONS)}"
        )
        return

    size_mb = document.file_size / (1024 * 1024)
    if size_mb > config.MAX_FILE_SIZE_MB:
        await update.message.reply_text(
            f"⚠️ {sc('file bahut badi hai')} ({human_size(document.file_size)}). "
            f"{sc('max limit:')} {config.MAX_FILE_SIZE_MB} MB."
        )
        return

    if not await check_subscribed(context.bot, user.id):
        await update.message.reply_text(
            f"🔔 {sc('bot use karne ke liye pehle channel join karo:')}",
            reply_markup=fsub_keyboard(),
        )
        return

    mark_action(user.id)

    await enqueue_job(
        chat_id,
        {
            "chat_id": chat_id,
            "user": user,
            "document": document,
            "file_name": file_name,
        },
        context.bot,
    )


async def process_archive_job(job: dict, bot):
    chat_id = job["chat_id"]
    document = job["document"]
    file_name = job["file_name"]

    user_dir = Path(config.DOWNLOAD_DIR) / str(chat_id)
    extract_dir = Path(config.EXTRACT_DIR) / str(chat_id) / uuid.uuid4().hex[:8]
    user_dir.mkdir(parents=True, exist_ok=True)
    archive_path = user_dir / f"{uuid.uuid4().hex[:8]}_{file_name}"

    status = await bot.send_message(
        chat_id=chat_id,
        text=f"⬇️ <b>{sc('downloading')}</b> {file_name}\n({human_size(document.file_size)})\n{progress_bar(0)}",
        parse_mode=ParseMode.HTML,
    )

    try:
        tg_file = await document.get_file()
        await tg_file.download_to_drive(custom_path=str(archive_path))
    except Exception as e:
        logger.exception("Download failed")
        await status.edit_text(f"❌ {sc('download fail ho gaya:')} {e}")
        security.cleanup(archive_path)
        return

    if security.needs_password(archive_path):
        PENDING_PASSWORD[chat_id] = {
            "archive_path": archive_path,
            "extract_dir": extract_dir,
            "file_name": file_name,
            "status_message": status,
            "timestamp": time.time(),
        }
        await status.edit_text(
            f"🔐 {sc('ye archive password-protected hai.')}\n{sc('neeche reply karke password bhejo.')}",
        )
        await bot.send_message(
            chat_id=chat_id,
            text=f"🔑 {sc('password bhejo:')}",
            reply_markup=ForceReply(selective=True),
        )
        return

    await run_extraction(bot, chat_id, archive_path, extract_dir, file_name, status, password=None)


async def run_extraction(bot, chat_id, archive_path: Path, extract_dir: Path, file_name: str, status, password=None):
    await status.edit_text(f"📦 <b>{sc('extracting')}</b> {file_name} ...", parse_mode=ParseMode.HTML)

    try:
        security.extract_archive(archive_path, extract_dir, password=password)
    except security.PasswordRequiredError:
        PENDING_PASSWORD[chat_id] = {
            "archive_path": archive_path, "extract_dir": extract_dir,
            "file_name": file_name, "status_message": status, "timestamp": time.time(),
        }
        await status.edit_text(f"🔐 {sc('password chahiye. neeche reply karke bhejo.')}")
        await bot.send_message(chat_id=chat_id, text=f"🔑 {sc('password bhejo:')}", reply_markup=ForceReply(selective=True))
        return
    except security.WrongPasswordError:
        await status.edit_text(f"❌ {sc('galat password. dubara /cancel karke file bhejo.')}")
        security.cleanup(archive_path, extract_dir)
        return
    except security.ArchiveTooLargeError as e:
        await status.edit_text(f"❌ {sc('zip-bomb protection:')} {e}")
        security.cleanup(archive_path, extract_dir)
        return
    except security.UnsafePathError:
        await status.edit_text(f"❌ {sc('is archive me unsafe/suspicious file paths hain — process nahi kiya.')}")
        security.cleanup(archive_path, extract_dir)
        return
    except security.UnsupportedArchiveError as e:
        await status.edit_text(f"❌ {e}")
        security.cleanup(archive_path, extract_dir)
        return
    except Exception as e:
        logger.exception("Extraction failed")
        await status.edit_text(f"❌ {sc('extraction fail ho gayi:')} {e}")
        security.cleanup(archive_path, extract_dir)
        return

    all_files = security.collect_files(extract_dir)
    security.cleanup(archive_path)  # archive ab nahi chahiye

    if not all_files:
        await status.edit_text(f"📭 {sc('archive khaali hai — koi file nahi mili.')}")
        security.cleanup(extract_dir)
        return

    total = len(all_files)
    truncated = total > config.MAX_FILES_TO_SEND
    total_size = sum(f.stat().st_size for f in all_files)

    job_id = uuid.uuid4().hex[:10]
    PENDING_JOBS[job_id] = {
        "chat_id": chat_id, "extract_dir": extract_dir,
        "all_files": all_files, "truncated": truncated, "total": total,
    }

    preview_names = "\n".join(f"  • {f.name}" for f in all_files[:10])
    more_note = f"\n  … {sc('aur')} {total - 10} {sc('files')}" if total > 10 else ""

    await status.edit_text(
        f"✅ <b>{total}</b> {sc('file(s) mili')} ({human_size(total_size)})\n\n"
        f"<code>{preview_names}{more_note}</code>\n\n"
        f"{sc('kaise bhejun?')}",
        parse_mode=ParseMode.HTML,
        reply_markup=preview_keyboard(job_id),
    )


# ============================================================
#  PASSWORD REPLY HANDLER
# ============================================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if await admin.handle_admin_text_input(update, context):
        return

    pending = PENDING_PASSWORD.get(chat_id)
    if pending:
        if time.time() - pending["timestamp"] > config.PASSWORD_TIMEOUT_SECONDS:
            PENDING_PASSWORD.pop(chat_id, None)
            security.cleanup(pending["archive_path"])
            await update.message.reply_text(f"⌛ {sc('password timeout ho gaya. dubara file bhejo.')}")
            return

        password = update.message.text.strip()
        PENDING_PASSWORD.pop(chat_id)
        try:
            await update.message.delete()  # privacy: password message hata do
        except Exception:
            pass
        await run_extraction(
            context.bot, chat_id, pending["archive_path"], pending["extract_dir"],
            pending["file_name"], pending["status_message"], password=password,
        )
        return

    await handle_unsupported_message(update, context)


async def handle_unsupported_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📦 {sc('mujhe ek archive file (.zip .rar .7z .tar) bhejo,')}\n"
        f"{sc('main uski saari files extract karke bhej dunga.')}\n\n"
        f"{sc('commands ke liye /help likho.')}"
    )


# ============================================================
#  PREVIEW → SEND FILES / SEND ZIP / CANCEL
# ============================================================
async def job_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # data format: job_send_<id> / job_zip_<id> / job_cancel_<id>
    parts = data.split("_", 2)
    action, job_id = parts[1], parts[2]

    job = PENDING_JOBS.pop(job_id, None)
    if not job:
        await query.edit_message_text(f"⚠️ {sc('ye job expire ho chuki hai.')}")
        return

    chat_id = job["chat_id"]
    extract_dir = job["extract_dir"]
    all_files = job["all_files"]
    truncated = job["truncated"]
    total = job["total"]
    files_to_send = all_files[: config.MAX_FILES_TO_SEND] if truncated else all_files

    if action == "cancel":
        security.cleanup(extract_dir)
        await query.edit_message_text(f"🛑 {sc('cancel ho gaya.')}")
        return

    if action == "zip":
        await query.edit_message_text(f"🗜 <b>{sc('zip ban raha hoon...')}</b>", parse_mode=ParseMode.HTML)
        zip_path = Path(config.REZIP_DIR) / str(chat_id) / f"{job_id}.zip"
        try:
            security.rezip_files(files_to_send, extract_dir, zip_path)
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
            with open(zip_path, "rb") as f:
                await context.bot.send_document(chat_id=chat_id, document=f, filename=f"extracted_{job_id}.zip")
            await db.increment_extractions(files_sent=len(files_to_send))
            await query.edit_message_text(f"🎉 <b>{sc('done!')}</b> {sc('zip bhej diya.')}", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.exception("Rezip/send failed")
            await query.edit_message_text(f"❌ {sc('zip banane/bhejne me error:')} {e}")
        finally:
            security.cleanup(extract_dir, zip_path)
        return

    # action == "send" -> individual files
    sent_count = 0
    last_edit = 0.0
    for file_path in files_to_send:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
            with open(file_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id, document=f, filename=file_path.name,
                    caption=str(file_path.relative_to(extract_dir)),
                )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send {file_path}: {e}")

        now = time.time()
        if now - last_edit > 1.5 or sent_count == len(files_to_send):
            pct = (sent_count / len(files_to_send)) * 100
            try:
                await query.edit_message_text(
                    f"📤 <b>{sc('sending files...')}</b>\n{progress_bar(pct)}  ({sent_count}/{len(files_to_send)})",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            last_edit = now

    await db.increment_extractions(files_sent=sent_count)

    final_msg = f"🎉 <b>{sc('done!')}</b> {sent_count}/{len(files_to_send)} {sc('file(s) bheji gayi.')}"
    if truncated:
        final_msg += (
            f"\n⚠️ {sc('archive me total')} {total} {sc('files thi, limit')} "
            f"({config.MAX_FILES_TO_SEND}) {sc('ki wajah se sirf kuch hi bheji gayi.')}"
        )
    await query.edit_message_text(final_msg, parse_mode=ParseMode.HTML)
    security.cleanup(extract_dir)


# ============================================================
#  ERROR HANDLER
# ============================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception", exc_info=context.error)
    if config.LOG_CHANNEL_ID:
        try:
            await context.bot.send_message(
                chat_id=config.LOG_CHANNEL_ID,
                text=f"⚠️ Unhandled error:\n<code>{context.error}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


# ============================================================
#  MAIN
# ============================================================
async def post_init(app):
    ok, err = await db.check_connection()
    if not ok:
        logger.error("MongoDB connection failed: %s", err)
        raise SystemExit(f"MongoDB se connect nahi ho paya: {err}")
    await db.init_db()
    logger.info("MongoDB connected and initialized.")


def main():
    if config.BOT_TOKEN.startswith("1234567890:"):
        raise SystemExit("config.py / .env me apna asli BOT_TOKEN daalo, phir bot chalao.")

    app = ApplicationBuilder().token(config.BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("admin", admin.admin_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND | filters.PHOTO | filters.VIDEO, handle_text)
    )
    app.add_error_handler(error_handler)

    logger.info("Bot started polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
