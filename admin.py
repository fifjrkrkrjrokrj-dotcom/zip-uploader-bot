"""
admin.py
--------
Admin panel: inline-button based. /admin command (sirf admins ke liye).

Features:
  - 📊 Analytics       — users, extractions, active users (today/week)
  - 🚫 Ban / ✅ Unban user (numeric user_id maangta hai)
  - 🛠 Maintenance mode ON/OFF (normal users ke liye bot pause)
  - ➕ Add admin / ➖ Remove admin (runtime, DB me persist hota hai)
  - 🏷 Set user tier (Free / VIP / Premium)
  - 📡 Activity feed toggle (user starts/messages/files admin ko forward)
  - 📢 Broadcast now (text/photo/document/video — copy_message se)
  - 🕐 Scheduled broadcast (status view — /schedulebroadcast se schedule karo)
  - 📜 Recent logs     — /logs command, chat me hi recent errors dikhata hai
  - 🗄 Backup now       — manual MongoDB backup trigger
  - 🗑 Delete all sent files — bot ne jo bhi files users ko bheji, sab chats
                              se delete kar deta hai (2-step confirmation)
"""

import asyncio
import html
import logging

from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.enums import ParseMode

import config
import database as db
import logbuffer
import state
from utils import to_small_caps as sc, DIVIDER

logger = logging.getLogger(__name__)

# Runtime admin set — config.ADMIN_IDS (env) + DB-persisted extra admins.
# load_extra_admins() DB se refresh karta hai (main.py se startup pe call hota hai).
_RUNTIME_ADMINS: set[int] = set(config.ADMIN_IDS)


async def load_extra_admins():
    """Startup pe DB se saved extra-admins load karta hai."""
    extra = await db.get_extra_admins()
    _RUNTIME_ADMINS.update(extra)
    logger.info("Loaded %d extra admin(s) from DB.", len(extra))


def is_admin(user_id: int) -> bool:
    return user_id in _RUNTIME_ADMINS


def admin_menu_keyboard(maintenance_on: bool, activity_feed_on: bool) -> InlineKeyboardMarkup:
    maint_label = "🛠 maintenance: on (tap to disable)" if maintenance_on else "🛠 maintenance: off (tap to enable)"
    feed_label = "📡 activity feed: on (tap to disable)" if activity_feed_on else "📡 activity feed: off (tap to enable)"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(sc("📊 analytics"), callback_data="admin_analytics")],
            [
                InlineKeyboardButton(sc("🚫 ban user"), callback_data="admin_ban"),
                InlineKeyboardButton(sc("✅ unban user"), callback_data="admin_unban"),
            ],
            [
                InlineKeyboardButton(sc("➕ add admin"), callback_data="admin_add_admin"),
                InlineKeyboardButton(sc("➖ remove admin"), callback_data="admin_remove_admin"),
            ],
            [InlineKeyboardButton(sc("🏷 set user tier (vip/premium)"), callback_data="admin_set_tier")],
            [InlineKeyboardButton(sc(maint_label), callback_data="admin_maintenance")],
            [InlineKeyboardButton(sc(feed_label), callback_data="admin_activity_feed")],
            [
                InlineKeyboardButton(sc("📢 broadcast now"), callback_data="admin_broadcast_now"),
                InlineKeyboardButton(sc("🕐 scheduled"), callback_data="admin_broadcast_scheduled"),
            ],
            [InlineKeyboardButton(sc("📜 recent logs"), callback_data="admin_logs")],
            [InlineKeyboardButton(sc("🗄 backup now"), callback_data="admin_backup_now")],
            [InlineKeyboardButton(sc("🗑 delete all sent files"), callback_data="admin_delete_sent_ask")],
        ]
    )


async def _render_home(target, edit: bool):
    """target: Message (edit=False, naya message bhejta hai) ya CallbackQuery (edit=True, message edit karta hai)."""
    maint = await db.get_maintenance()
    feed = await db.get_activity_feed()
    text = f"✦  <b>{sc('admin panel')}</b>  ✦\n{DIVIDER}"
    markup = admin_menu_keyboard(maint, feed)
    if edit:
        await target.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def admin_command(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    await _render_home(message, edit=False)


async def logs_command(client, message: Message):
    """/logs — recent WARNING/ERROR log lines seedha chat me."""
    if not is_admin(message.from_user.id):
        return
    lines = logbuffer.recent(20)
    if not lines:
        await message.reply_text(f"✅ {sc('koi recent error/warning nahi hai.')}")
        return
    body = html.escape("\n".join(lines))
    # Telegram message limit ~4096 chars — zyada purane trim kar do.
    if len(body) > 3500:
        body = body[-3500:]
    await message.reply_text(f"📜 <b>{sc('recent logs')}</b>\n<pre>{body}</pre>", parse_mode=ParseMode.HTML)


async def admin_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        await callback_query.answer(sc("sirf admin ke liye."), show_alert=True)
        return
    await callback_query.answer()
    data = callback_query.data
    user_data = state.get_user_data(user_id)

    if data == "admin_analytics":
        a = await db.get_analytics_summary()
        text = (
            f"✦  <b>{sc('analytics')}</b>  ✦\n{DIVIDER}\n\n"
            f"👥 <b>{sc('total users:')}</b> {a['total_users']}\n"
            f"🚫 <b>{sc('banned:')}</b> {a['banned_users']}\n\n"
            f"📦 <b>{sc('total extractions:')}</b> {a['total_extractions']}\n"
            f"🗂 <b>{sc('total files sent:')}</b> {a['total_files_sent']}\n\n"
            f"📅 <b>{sc('today —')}</b> {sc('active:')} {a['today_active']}, "
            f"{sc('extractions:')} {a['today_extractions']}\n"
            f"🗓 <b>{sc('last 7 days —')}</b> {sc('active:')} {a['week_active']}, "
            f"{sc('extractions:')} {a['week_extractions']}"
        )
        await callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ back"), callback_data="admin_home")]]),
        )

    elif data == "admin_ban":
        user_data["awaiting_ban_id"] = True
        await callback_query.edit_message_text(
            f"🚫 {sc('jis user ko ban karna hai uski numeric telegram id message me bhejo.')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ cancel"), callback_data="admin_home")]]),
        )

    elif data == "admin_unban":
        user_data["awaiting_unban_id"] = True
        await callback_query.edit_message_text(
            f"✅ {sc('jis user ko unban karna hai uski numeric telegram id message me bhejo.')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ cancel"), callback_data="admin_home")]]),
        )

    elif data == "admin_add_admin":
        user_data["awaiting_add_admin_id"] = True
        await callback_query.edit_message_text(
            f"➕ {sc('jise admin banana hai uski numeric telegram id bhejo.')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ cancel"), callback_data="admin_home")]]),
        )

    elif data == "admin_remove_admin":
        user_data["awaiting_remove_admin_id"] = True
        await callback_query.edit_message_text(
            f"➖ {sc('jis admin ko hataana hai uski numeric telegram id bhejo.')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ cancel"), callback_data="admin_home")]]),
        )

    elif data == "admin_set_tier":
        user_data["awaiting_tier_user_id"] = True
        await callback_query.edit_message_text(
            f"🏷 {sc('jis user ka tier badalna hai uski numeric telegram id bhejo.')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ cancel"), callback_data="admin_home")]]),
        )

    elif data.startswith("admin_tier_"):
        # format: admin_tier_<tier>_<uid>
        _, _, tier, uid_str = data.split("_", 3)
        uid = int(uid_str)
        ok = await db.set_user_tier(uid, tier)
        if ok:
            await callback_query.edit_message_text(
                f"✅ {sc('tier set ho gaya:')} <code>{uid}</code> → <b>{tier}</b>", parse_mode=ParseMode.HTML
            )
            try:
                await client.send_message(
                    chat_id=uid,
                    text=f"🎉 {sc('aapka account ab')} <b>{tier.upper()}</b> {sc('tier me upgrade ho gaya hai!')}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        else:
            await callback_query.edit_message_text(f"⚠️ {sc('user nahi mila.')}")

    elif data == "admin_broadcast_now":
        user_data["awaiting_broadcast_message"] = True
        await callback_query.edit_message_text(
            f"📢 {sc('ab jo bhi message bhejo (text / photo / document / video) — wahi sabhi users ko broadcast ho jaayega.')}\n"
            f"{sc('cancel karna ho to /cancel likho.')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ cancel"), callback_data="admin_home")]]),
        )

    elif data == "admin_broadcast_scheduled":
        pending = await db.get_pending_scheduled_broadcasts()
        if not pending:
            body = sc("koi scheduled broadcast pending nahi hai.")
        else:
            lines = [f"  • {p['run_at'].strftime('%Y-%m-%d %H:%M UTC')}" for p in pending]
            body = "\n".join(lines)
        await callback_query.edit_message_text(
            f"🕐 <b>{sc('scheduled broadcasts')}</b>\n{DIVIDER}\n\n<code>{body}</code>\n\n"
            f"{sc('naya schedule karne ke liye: kisi message ko REPLY karke likho')}\n"
            f"<code>/schedulebroadcast YYYY-MM-DD HH:MM</code> ({sc('UTC time')})",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ back"), callback_data="admin_home")]]),
        )

    elif data == "admin_maintenance":
        current = await db.get_maintenance()
        await db.set_maintenance(not current)
        await _render_home(callback_query, edit=True)

    elif data == "admin_activity_feed":
        current = await db.get_activity_feed()
        await db.set_activity_feed(not current)
        await _render_home(callback_query, edit=True)

    elif data == "admin_logs":
        lines = logbuffer.recent(20)
        if not lines:
            body = sc("koi recent error/warning nahi hai.")
            text = f"📜 <b>{sc('recent logs')}</b>\n\n{body}"
        else:
            body = html.escape("\n".join(lines))
            if len(body) > 3000:
                body = body[-3000:]
            text = f"📜 <b>{sc('recent logs')}</b>\n<pre>{body}</pre>"
        await callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ back"), callback_data="admin_home")]]),
        )

    elif data == "admin_backup_now":
        await callback_query.edit_message_text(f"🗄 {sc('backup ban raha hai, thoda ruko...')}")
        import backup  # local import — avoids circular import at module load
        try:
            await backup.run_backup(client)
            await _render_home(callback_query, edit=True)
        except Exception as e:
            logger.exception("Manual backup failed")
            await callback_query.edit_message_text(
                f"❌ {sc('backup fail ho gaya:')} {e}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ back"), callback_data="admin_home")]]),
            )

    elif data == "admin_delete_sent_ask":
        count = await db.count_sent_messages()
        await callback_query.edit_message_text(
            f"⚠️ <b>{sc('confirm')}</b>\n\n"
            f"{sc('ye bot ke bheje hue')} <b>{count}</b> {sc('file message(s) sabhi chats se PERMANENTLY delete kar dega.')}\n"
            f"{sc('ye action undo nahi ho sakta. aage badhein?')}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(sc("🗑 haan, sab delete karo"), callback_data="admin_delete_sent_confirm")],
                    [InlineKeyboardButton(sc("⬅️ cancel"), callback_data="admin_home")],
                ]
            ),
        )

    elif data == "admin_delete_sent_confirm":
        await callback_query.edit_message_text(f"🗑 {sc('files delete ki ja rahi hain...')}")
        deleted, failed = await _delete_all_sent_files(client)
        await callback_query.edit_message_text(
            f"✅ {sc('done.')} {sc('deleted:')} {deleted} | {sc('failed/already-gone:')} {failed}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(sc("⬅️ back"), callback_data="admin_home")]]),
        )

    elif data == "admin_home":
        await _render_home(callback_query, edit=True)


async def _delete_all_sent_files(client) -> tuple[int, int]:
    """Bot ne jo bhi files (documents) users ko bheji thi, sab delete karta hai."""
    records = await db.get_all_sent_messages()
    semaphore = asyncio.Semaphore(15)
    deleted, failed = 0, 0

    async def _delete_one(rec: dict):
        nonlocal deleted, failed
        async with semaphore:
            try:
                await client.delete_messages(chat_id=rec["chat_id"], message_ids=rec["message_id"])
                deleted += 1
            except Exception:
                failed += 1
            finally:
                await db.delete_sent_message_record(rec["_id"])
            await asyncio.sleep(0.05)

    await asyncio.gather(*(_delete_one(r) for r in records))
    return deleted, failed


async def handle_admin_text_input(client, message: Message) -> bool:
    """
    Ban/unban/add-admin/remove-admin/tier/broadcast ke liye pending multi-step
    admin flows handle karta hai. Returns True agar isne message consume kar liya.
    """
    user_id = message.from_user.id
    if not is_admin(user_id):
        return False

    user_data = state.get_user_data(user_id)
    text = (message.text or "").strip()

    if user_data.pop("awaiting_ban_id", False):
        if not text.isdigit():
            await message.reply_text(sc("valid numeric user id bhejo."))
            return True
        ok = await db.ban_user(int(text))
        await message.reply_text(f"✅ {sc('user ban ho gaya:')} {text}" if ok else f"⚠️ {sc('user nahi mila.')}")
        return True

    if user_data.pop("awaiting_unban_id", False):
        if not text.isdigit():
            await message.reply_text(sc("valid numeric user id bhejo."))
            return True
        ok = await db.unban_user(int(text))
        await message.reply_text(f"✅ {sc('user unban ho gaya:')} {text}" if ok else f"⚠️ {sc('user nahi mila.')}")
        return True

    if user_data.pop("awaiting_add_admin_id", False):
        if not text.isdigit():
            await message.reply_text(sc("valid numeric user id bhejo."))
            return True
        uid = int(text)
        _RUNTIME_ADMINS.add(uid)
        await db.add_extra_admin(uid)
        await message.reply_text(f"✅ {sc('naya admin add ho gaya:')} {text}")
        try:
            await client.send_message(chat_id=uid, text=f"🎉 {sc('aapko is bot ka admin bana diya gaya hai.')}")
        except Exception:
            pass
        return True

    if user_data.pop("awaiting_remove_admin_id", False):
        if not text.isdigit():
            await message.reply_text(sc("valid numeric user id bhejo."))
            return True
        uid = int(text)
        if uid == config.OWNER_ID:
            await message.reply_text(f"⚠️ {sc('owner ko remove nahi kar sakte.')}")
            return True
        _RUNTIME_ADMINS.discard(uid)
        await db.remove_extra_admin(uid)
        await message.reply_text(f"✅ {sc('admin remove ho gaya:')} {text}")
        return True

    if user_data.pop("awaiting_tier_user_id", False):
        if not text.isdigit():
            await message.reply_text(sc("valid numeric user id bhejo."))
            return True
        uid = int(text)
        await message.reply_text(
            f"🏷 {sc('is user ke liye tier chuno:')} <code>{uid}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🆓 Free", callback_data=f"admin_tier_free_{uid}"),
                        InlineKeyboardButton("⭐ VIP", callback_data=f"admin_tier_vip_{uid}"),
                        InlineKeyboardButton("💎 Premium", callback_data=f"admin_tier_premium_{uid}"),
                    ]
                ]
            ),
        )
        return True

    if user_data.get("awaiting_broadcast_message"):
        user_data.pop("awaiting_broadcast_message")
        await execute_broadcast_from_message(client, message)
        return True

    return False


async def execute_broadcast_from_message(client, message: Message) -> tuple[int, int]:
    """Kisi bhi message (text/photo/document/video/...) ko sabhi non-banned users ko copy_message se broadcast karta hai."""
    return await execute_broadcast_copy(client, message.chat.id, message.id, reply_status_to=message)


async def execute_broadcast_copy(client, from_chat_id: int, message_id: int, reply_status_to=None) -> tuple[int, int]:
    """copy_message use karta hai — text/photo/document/video/etc sab uniformly handle ho jaate hain."""
    user_ids = await db.get_all_user_ids()
    sent, failed = 0, 0
    status = None
    if reply_status_to is not None:
        status = await reply_status_to.reply_text(f"📣 Broadcasting to {len(user_ids)} users...")

    semaphore = asyncio.Semaphore(20)

    async def send_one(uid: int):
        nonlocal sent, failed
        async with semaphore:
            try:
                await client.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=message_id)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)

    await asyncio.gather(*(send_one(uid) for uid in user_ids))
    if status is not None:
        await status.edit_text(f"✅ Broadcast complete.\nSent: {sent} | Failed: {failed}")
    return sent, failed
