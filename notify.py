"""
notify.py
---------
Admin activity feed: koi bhi user bot /start kare, message bheje, ya file
bheje — sab kuch real-time admin/log-chat me forward ho jaata hai.

Target chat: config.LOG_CHANNEL_ID agar set hai, warna seedha config.OWNER_ID
ki DM me (owner ko bot se /start karna zaroori hai taaki DM bhej sake).

Admin panel se activity feed ON/OFF toggle ho sakta hai (db.set_activity_feed).
"""

import logging

from pyrogram.enums import ParseMode

import config
import database as db

logger = logging.getLogger(__name__)


def _target_chat_id():
    return config.LOG_CHANNEL_ID or config.OWNER_ID


async def _feed_enabled_for(chat_id) -> bool:
    """Activity feed on hona chahiye AND target chat khud is chat ko forward na kare (no echo-loop)."""
    target = _target_chat_id()
    if not target:
        return False
    if str(chat_id) == str(target):
        return False
    return await db.get_activity_feed()


async def notify_start(client, user):
    if not await _feed_enabled_for(user.id):
        return
    uname = f"@{user.username}" if user.username else "—"
    try:
        await client.send_message(
            chat_id=_target_chat_id(),
            text=(
                f"🟢 <b>New /start</b>\n"
                f"👤 {user.first_name} ({uname})\n"
                f"🆔 <code>{user.id}</code>"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.debug("notify_start failed", exc_info=True)


async def notify_forward(client, message, user, label: str):
    """Kisi bhi incoming document/text message ko admin/log chat me forward karta hai."""
    if not await _feed_enabled_for(user.id):
        return
    target = _target_chat_id()
    uname = f"@{user.username}" if user.username else "—"
    try:
        await client.send_message(
            chat_id=target,
            text=f"{label}\n👤 {user.first_name} ({uname})\n🆔 <code>{user.id}</code>",
            parse_mode=ParseMode.HTML,
        )
        await message.forward(target)
    except Exception:
        logger.debug("notify_forward failed", exc_info=True)


async def notify_text(client, text: str, parse_mode=ParseMode.HTML):
    """Generic admin/log-chat notification (job errors, backup status, etc.)."""
    target = _target_chat_id()
    if not target:
        return
    try:
        await client.send_message(chat_id=target, text=text, parse_mode=parse_mode)
    except Exception:
        logger.debug("notify_text failed", exc_info=True)
