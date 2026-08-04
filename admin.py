"""
admin.py
--------
Admin panel: inline-button based. /admin command (sirf ADMIN_IDS ke liye).

Features:
  - 📊 Analytics  — users, extractions, active users (today/week)
  - 🚫 Ban / ✅ Unban user (numeric user_id maangta hai)
  - 🛠 Maintenance mode ON/OFF (normal users ke liye bot pause)
  - 📢 Broadcast (existing /broadcast command ka shortcut)
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
import database as db
from utils import to_small_caps as sc, DIVIDER


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def admin_menu_keyboard(maintenance_on: bool) -> InlineKeyboardMarkup:
    maint_label = "🛠 maintenance: on (tap to disable)" if maintenance_on else "🛠 maintenance: off (tap to enable)"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(sc("📊 analytics"), callback_data="admin_analytics", style="primary")],
            [
                InlineKeyboardButton(sc("🚫 ban user"), callback_data="admin_ban", style="danger"),
                InlineKeyboardButton(sc("✅ unban user"), callback_data="admin_unban", style="success"),
            ],
            [InlineKeyboardButton(sc(maint_label), callback_data="admin_maintenance", style="primary")],
            [InlineKeyboardButton(sc("📢 broadcast"), callback_data="admin_broadcast_hint", style="primary")],
        ]
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    maint = await db.get_maintenance()
    await update.message.reply_text(
        f"✦  <b>{sc('admin panel')}</b>  ✦\n{DIVIDER}",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_menu_keyboard(maint),
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer(sc("sirf admin ke liye."), show_alert=True)
        return
    await query.answer()
    data = query.data

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
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(sc("⬅️ back"), callback_data="admin_home")]]
            ),
        )

    elif data == "admin_ban":
        context.user_data["awaiting_ban_id"] = True
        await query.edit_message_text(
            f"🚫 {sc('jis user ko ban karna hai uski numeric telegram id message me bhejo.')}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(sc("⬅️ cancel"), callback_data="admin_home")]]
            ),
        )

    elif data == "admin_unban":
        context.user_data["awaiting_unban_id"] = True
        await query.edit_message_text(
            f"✅ {sc('jis user ko unban karna hai uski numeric telegram id message me bhejo.')}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(sc("⬅️ cancel"), callback_data="admin_home")]]
            ),
        )

    elif data == "admin_maintenance":
        current = await db.get_maintenance()
        await db.set_maintenance(not current)
        maint = not current
        await query.edit_message_text(
            f"✦  <b>{sc('admin panel')}</b>  ✦\n{DIVIDER}\n\n"
            f"🛠 {sc('maintenance mode ab')} <b>{sc('on') if maint else sc('off')}</b> {sc('hai.')}",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_menu_keyboard(maint),
        )

    elif data == "admin_broadcast_hint":
        await query.edit_message_text(
            f"📢 {sc('broadcast karne ke liye likho:')}\n<code>/broadcast your message</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(sc("⬅️ back"), callback_data="admin_home")]]
            ),
        )

    elif data == "admin_home":
        maint = await db.get_maintenance()
        await query.edit_message_text(
            f"✦  <b>{sc('admin panel')}</b>  ✦\n{DIVIDER}",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_menu_keyboard(maint),
        )


async def handle_admin_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Ban/unban ke liye numeric ID input handle karta hai.
    Returns True agar isne message consume kar liya (aage handler chalne ki zaroorat nahi).
    """
    if not is_admin(update.effective_user.id):
        return False

    text = (update.message.text or "").strip()

    if context.user_data.pop("awaiting_ban_id", False):
        if not text.isdigit():
            await update.message.reply_text(sc("valid numeric user id bhejo."))
            return True
        ok = await db.ban_user(int(text))
        await update.message.reply_text(
            f"✅ {sc('user ban ho gaya:')} {text}" if ok else f"⚠️ {sc('user nahi mila.')}"
        )
        return True

    if context.user_data.pop("awaiting_unban_id", False):
        if not text.isdigit():
            await update.message.reply_text(sc("valid numeric user id bhejo."))
            return True
        ok = await db.unban_user(int(text))
        await update.message.reply_text(
            f"✅ {sc('user unban ho gaya:')} {text}" if ok else f"⚠️ {sc('user nahi mila.')}"
        )
        return True

    return False
