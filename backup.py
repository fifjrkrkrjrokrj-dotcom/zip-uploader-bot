"""
backup.py
---------
Scheduled MongoDB backup taaki data safe rahe.

- Agar server pe `mongodump` binary available hai to full native dump leta hai.
- Warna sabhi collections ko JSON me export karke fallback backup banata hai.
- Backup ek .zip me pack hoke config.LOG_CHANNEL_ID (ya owner DM) me bhej diya
  jaata hai, aur local disk pe sirf latest BACKUP_KEEP_LOCAL copies rakhi jaati hain.

BACKUP_INTERVAL_HOURS=0 karne se auto-backup disabled ho jaata hai (sirf
/admin panel se "backup now" manual trigger available rehta hai).
"""

import asyncio
import json
import logging
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import config
import database as db

logger = logging.getLogger(__name__)


async def _export_json_backup(dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    collections = {
        "users": db.users_col,
        "stats": db.stats_col,
        "daily_stats": db.daily_col,
        "flags": db.flags_col,
        "history": db.history_col,
        "sent_messages": db.sent_messages_col,
    }
    for name, col in collections.items():
        docs = [d async for d in col.find()]
        for d in docs:
            d["_id"] = str(d["_id"])
        (dest_dir / f"{name}.json").write_text(
            json.dumps(docs, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )


def _try_mongodump(dest_dir: Path) -> bool:
    if not shutil.which("mongodump"):
        return False
    try:
        subprocess.run(
            ["mongodump", "--uri", config.MONGO_URI, "--out", str(dest_dir)],
            check=True,
            capture_output=True,
            timeout=300,
        )
        return True
    except Exception as e:
        logger.warning("mongodump failed (%s), falling back to JSON export.", e)
        return False


async def run_backup(client=None) -> Path | None:
    """Ek backup zip banata hai, admin/log chat me bhejta hai, aur zip path return karta hai."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_dir = Path(config.BACKUP_DIR)
    base_dir.mkdir(parents=True, exist_ok=True)
    work_dir = base_dir / f"tmp_backup_{ts}"

    used_mongodump = await asyncio.to_thread(_try_mongodump, work_dir)
    if not used_mongodump:
        await _export_json_backup(work_dir)

    zip_path = base_dir / f"backup_{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in work_dir.rglob("*"):
            if f.is_file():
                zf.write(f, arcname=str(f.relative_to(work_dir)))
    shutil.rmtree(work_dir, ignore_errors=True)

    if client is not None:
        import notify  # local import to avoid circulars at module load time

        target = config.LOG_CHANNEL_ID or config.OWNER_ID
        if target:
            try:
                await client.send_document(
                    chat_id=target,
                    document=str(zip_path),
                    file_name=zip_path.name,
                    caption=f"🗄 MongoDB backup — {ts} UTC ({'mongodump' if used_mongodump else 'json export'})",
                )
            except Exception as e:
                logger.error("Failed to deliver backup to admin/log chat: %s", e)
                await notify.notify_text(client, f"⚠️ Backup created but failed to deliver: {e}")

    # purane local backups clean up, sirf latest N rakho
    all_backups = sorted(base_dir.glob("backup_*.zip"))
    for old in all_backups[: max(0, len(all_backups) - config.BACKUP_KEEP_LOCAL)]:
        try:
            old.unlink()
        except Exception:
            pass

    return zip_path


async def backup_scheduler(client):
    """Background loop — main.py se asyncio task ke roop me start hota hai."""
    if config.BACKUP_INTERVAL_HOURS <= 0:
        logger.info("Auto-backup disabled (BACKUP_INTERVAL_HOURS <= 0).")
        return

    logger.info("Auto MongoDB backup scheduler started (every %sh).", config.BACKUP_INTERVAL_HOURS)
    while True:
        await asyncio.sleep(config.BACKUP_INTERVAL_HOURS * 3600)
        try:
            await run_backup(client)
            logger.info("Auto-backup completed.")
        except Exception:
            logger.exception("Auto-backup failed")
