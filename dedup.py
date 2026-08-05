"""
dedup.py
--------
Duplicate-archive detection.

Telegram khud guarantee karta hai ki same physical file ka `file_unique_id`
hamesha same rehta hai — chahe wo file dobara upload/forward ho, kitni bhi
baar. Isliye hum bina dobara download/scan/extract kiye hi jaan sakte hain
ki ye exact archive pehle kisi ne bheji thi (isi bot ke through).

Match milne par bot cached (pehle se extracted) folder se seedha serve kar
deta hai — bandwidth, ClamAV scan time, aur CPU sab bachta hai (khaaskar
bade 1GB+ files ke liye ye bahut faayde ka hai).

Cache config.CACHE_DIR/<file_unique_id>/ me disk pe rehta hai, aur
config.CACHE_TTL_HOURS baad (background sweep se) auto-expire ho jaata hai.
"""

import asyncio
import logging
import shutil
from pathlib import Path

import config
import database as db

logger = logging.getLogger(__name__)


def cache_dir_for(file_unique_id: str) -> Path:
    return Path(config.CACHE_DIR) / file_unique_id


async def get_cache_hit(file_unique_id: str) -> dict | None:
    """Cache me valid entry ho to doc return karta hai, warna None."""
    if not config.CACHE_ENABLED:
        return None
    doc = await db.get_cached_archive(file_unique_id)
    if not doc:
        return None
    d = Path(doc["extract_dir"])
    if not d.exists() or not any(d.iterdir()):
        # Cache record hai lekin disk pe data missing (server restart / manual clean) — stale.
        await db.delete_cached_archive(file_unique_id)
        return None
    return doc


async def store_cache(file_unique_id: str, extract_dir: Path, file_name: str):
    if not config.CACHE_ENABLED:
        return
    await db.cache_archive(file_unique_id, str(extract_dir), file_name)


async def cache_cleanup_scheduler():
    """Background loop — expired cache entries disk + DB se clean karta hai."""
    if not config.CACHE_ENABLED or config.CACHE_TTL_HOURS <= 0:
        logger.info("Archive dedup-cache expiry disabled.")
        return
    logger.info("Dedup-cache cleanup scheduler started (TTL=%sh).", config.CACHE_TTL_HOURS)
    while True:
        await asyncio.sleep(3600)  # hourly sweep
        try:
            expired = await db.get_expired_cache_entries(config.CACHE_TTL_HOURS)
            for doc in expired:
                shutil.rmtree(doc["extract_dir"], ignore_errors=True)
                await db.delete_cached_archive(doc["file_unique_id"])
            if expired:
                logger.info("Expired %d cached archive(s).", len(expired))
        except Exception:
            logger.exception("Cache cleanup sweep failed")
