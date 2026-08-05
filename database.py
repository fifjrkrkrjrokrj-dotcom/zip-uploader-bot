"""
database.py
-----------
MongoDB wrapper (motor — async driver).

Collections:
  - users         : har user ka record (broadcast + stats + ban status + language)
  - stats         : global counters (total_extractions, total_files_sent)
  - daily_stats   : date-wise analytics (active users, extractions)
  - flags         : runtime toggles (maintenance_mode, extra_admins, activity_feed)
  - history       : per-user extraction history
  - sent_messages : bot ne jo files bheji unke (chat_id, message_id) — bulk-delete ke liye
"""

from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

import config

_client = AsyncIOMotorClient(config.MONGO_URI, serverSelectionTimeoutMS=8000)
_db = _client[config.MONGO_DB_NAME]

users_col = _db["users"]
stats_col = _db["stats"]
daily_col = _db["daily_stats"]
flags_col = _db["flags"]
history_col = _db["history"]
sent_messages_col = _db["sent_messages"]
cache_col = _db["archive_cache"]
scheduled_broadcasts_col = _db["scheduled_broadcasts"]


async def check_connection() -> tuple[bool, str]:
    """Startup pe DB reachable hai ya nahi check karta hai."""
    try:
        await _client.admin.command("ping")
        return True, ""
    except PyMongoError as e:
        return False, str(e)


async def init_db():
    """Indexes create karta hai. Bot start hote hi ek baar call hota hai."""
    await users_col.create_index("user_id", unique=True)
    await daily_col.create_index("date", unique=True)
    await history_col.create_index("user_id")
    await sent_messages_col.create_index("chat_id")
    await cache_col.create_index("file_unique_id", unique=True)
    await scheduled_broadcasts_col.create_index("run_at")
    await stats_col.update_one(
        {"_id": "counters"},
        {"$setOnInsert": {"total_extractions": 0, "total_files_sent": 0}},
        upsert=True,
    )
    await flags_col.update_one(
        {"_id": "runtime"},
        {
            "$setOnInsert": {
                "maintenance_mode": False,
                "extra_admins": [],
                "activity_feed": config.ADMIN_ACTIVITY_FEED_DEFAULT,
            }
        },
        upsert=True,
    )


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------- USERS ----------------
async def add_user(user_id: int, first_name: str, username: str | None):
    await users_col.update_one(
        {"user_id": user_id},
        {
            "$setOnInsert": {
                "user_id": user_id,
                "first_name": first_name,
                "username": username or "",
                "banned": False,
                "lang": config.DEFAULT_LANGUAGE,
                "tier": "free",
                "joined_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


async def get_all_user_ids() -> list[int]:
    cursor = users_col.find({"banned": {"$ne": True}}, {"user_id": 1, "_id": 0})
    return [doc["user_id"] async for doc in cursor]


async def get_user_count() -> int:
    return await users_col.count_documents({})


async def is_banned(user_id: int) -> bool:
    doc = await users_col.find_one({"user_id": user_id}, {"banned": 1})
    return bool(doc and doc.get("banned"))


async def ban_user(user_id: int) -> bool:
    res = await users_col.update_one({"user_id": user_id}, {"$set": {"banned": True}})
    return res.matched_count > 0


async def unban_user(user_id: int) -> bool:
    res = await users_col.update_one({"user_id": user_id}, {"$set": {"banned": False}})
    return res.matched_count > 0


async def get_banned_count() -> int:
    return await users_col.count_documents({"banned": True})


# ---------------- LANGUAGE ----------------
async def get_user_lang(user_id: int) -> str:
    doc = await users_col.find_one({"user_id": user_id}, {"lang": 1})
    return (doc or {}).get("lang") or config.DEFAULT_LANGUAGE


async def set_user_lang(user_id: int, lang: str):
    await users_col.update_one({"user_id": user_id}, {"$set": {"lang": lang}}, upsert=True)


# ---------------- STATS / ANALYTICS ----------------
async def increment_extractions(files_sent: int = 0):
    await stats_col.update_one(
        {"_id": "counters"},
        {"$inc": {"total_extractions": 1, "total_files_sent": files_sent}},
        upsert=True,
    )
    await daily_col.update_one(
        {"date": _today()},
        {"$inc": {"extractions": 1, "files_sent": files_sent}},
        upsert=True,
    )


async def log_active_user(user_id: int):
    """Aaj ke active users me user_id add karta hai (set-based, duplicate-safe)."""
    await daily_col.update_one(
        {"date": _today()},
        {"$addToSet": {"active_users": user_id}},
        upsert=True,
    )


async def get_total_extractions() -> int:
    doc = await stats_col.find_one({"_id": "counters"})
    return doc["total_extractions"] if doc else 0


async def get_analytics_summary() -> dict:
    counters = await stats_col.find_one({"_id": "counters"}) or {}
    today_doc = await daily_col.find_one({"date": _today()}) or {}
    last7_cursor = daily_col.find().sort("date", -1).limit(7)
    last7 = [d async for d in last7_cursor]
    week_extractions = sum(d.get("extractions", 0) for d in last7)
    week_active = len({u for d in last7 for u in d.get("active_users", [])})

    return {
        "total_users": await get_user_count(),
        "banned_users": await get_banned_count(),
        "total_extractions": counters.get("total_extractions", 0),
        "total_files_sent": counters.get("total_files_sent", 0),
        "today_active": len(today_doc.get("active_users", [])),
        "today_extractions": today_doc.get("extractions", 0),
        "week_active": week_active,
        "week_extractions": week_extractions,
    }


# ---------------- MAINTENANCE MODE ----------------
async def get_maintenance() -> bool:
    doc = await flags_col.find_one({"_id": "runtime"})
    return bool(doc and doc.get("maintenance_mode"))


async def set_maintenance(enabled: bool):
    await flags_col.update_one(
        {"_id": "runtime"}, {"$set": {"maintenance_mode": enabled}}, upsert=True
    )


# ---------------- ACTIVITY FEED TOGGLE ----------------
async def get_activity_feed() -> bool:
    doc = await flags_col.find_one({"_id": "runtime"})
    if doc is None or "activity_feed" not in doc:
        return config.ADMIN_ACTIVITY_FEED_DEFAULT
    return bool(doc.get("activity_feed"))


async def set_activity_feed(enabled: bool):
    await flags_col.update_one(
        {"_id": "runtime"}, {"$set": {"activity_feed": enabled}}, upsert=True
    )


# ---------------- RUNTIME EXTRA ADMINS ----------------
async def get_extra_admins() -> list[int]:
    doc = await flags_col.find_one({"_id": "runtime"}, {"extra_admins": 1})
    return list((doc or {}).get("extra_admins", []))


async def add_extra_admin(user_id: int):
    await flags_col.update_one(
        {"_id": "runtime"}, {"$addToSet": {"extra_admins": user_id}}, upsert=True
    )


async def remove_extra_admin(user_id: int) -> bool:
    res = await flags_col.update_one(
        {"_id": "runtime"}, {"$pull": {"extra_admins": user_id}}
    )
    return res.modified_count > 0


# ---------------- PER-USER HISTORY ----------------
async def add_history(user_id: int, file_name: str, files_count: int, size_bytes: int, delivery: str):
    await history_col.insert_one(
        {
            "user_id": user_id,
            "file_name": file_name,
            "files_count": files_count,
            "size_bytes": size_bytes,
            "delivery": delivery,  # "files" ya "zip"
            "at": datetime.now(timezone.utc),
        }
    )


async def get_user_history(user_id: int, limit: int = 10) -> list[dict]:
    cursor = history_col.find({"user_id": user_id}).sort("at", -1).limit(limit)
    return [doc async for doc in cursor]


# ---------------- SENT MESSAGES (bulk-delete support) ----------------
async def add_sent_message(chat_id: int, message_id: int, kind: str = "document"):
    await sent_messages_col.insert_one(
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "kind": kind,
            "at": datetime.now(timezone.utc),
        }
    )


async def get_all_sent_messages() -> list[dict]:
    cursor = sent_messages_col.find({}, {"chat_id": 1, "message_id": 1, "_id": 1})
    return [doc async for doc in cursor]


async def delete_sent_message_record(doc_id):
    await sent_messages_col.delete_one({"_id": doc_id})


async def count_sent_messages() -> int:
    return await sent_messages_col.count_documents({})


async def clear_sent_messages():
    await sent_messages_col.delete_many({})


# ---------------- USER TIERS (VIP / premium) ----------------
async def get_user_tier(user_id: int) -> str:
    doc = await users_col.find_one({"user_id": user_id}, {"tier": 1})
    return (doc or {}).get("tier") or "free"


async def set_user_tier(user_id: int, tier: str) -> bool:
    res = await users_col.update_one({"user_id": user_id}, {"$set": {"tier": tier}})
    return res.matched_count > 0


async def get_tier_counts() -> dict:
    cursor = users_col.aggregate([{"$group": {"_id": "$tier", "count": {"$sum": 1}}}])
    counts = {"free": 0, "vip": 0, "premium": 0}
    async for doc in cursor:
        counts[doc["_id"] or "free"] = doc["count"]
    return counts


# ---------------- DUPLICATE-DETECTION CACHE ----------------
async def get_cached_archive(file_unique_id: str) -> dict | None:
    return await cache_col.find_one({"file_unique_id": file_unique_id})


async def cache_archive(file_unique_id: str, extract_dir: str, file_name: str):
    await cache_col.update_one(
        {"file_unique_id": file_unique_id},
        {"$set": {"extract_dir": extract_dir, "file_name": file_name, "cached_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def delete_cached_archive(file_unique_id: str):
    await cache_col.delete_one({"file_unique_id": file_unique_id})


async def get_expired_cache_entries(ttl_hours: float) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    cursor = cache_col.find({"cached_at": {"$lt": cutoff}})
    return [d async for d in cursor]


# ---------------- SCHEDULED BROADCASTS ----------------
async def add_scheduled_broadcast(run_at: datetime, from_chat_id: int, message_id: int) -> str:
    res = await scheduled_broadcasts_col.insert_one(
        {
            "run_at": run_at,
            "from_chat_id": from_chat_id,
            "message_id": message_id,
            "sent": False,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return str(res.inserted_id)


async def get_due_scheduled_broadcasts(now: datetime) -> list[dict]:
    cursor = scheduled_broadcasts_col.find({"sent": False, "run_at": {"$lte": now}})
    return [d async for d in cursor]


async def get_pending_scheduled_broadcasts() -> list[dict]:
    cursor = scheduled_broadcasts_col.find({"sent": False}).sort("run_at", 1)
    return [d async for d in cursor]


async def mark_scheduled_broadcast_sent(doc_id):
    await scheduled_broadcasts_col.update_one({"_id": doc_id}, {"$set": {"sent": True}})
