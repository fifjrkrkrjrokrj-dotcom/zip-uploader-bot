"""
database.py
-----------
MongoDB wrapper (motor — async driver).

Collections:
  - users : har user ka record (broadcast + stats + ban status)
  - stats : global counters (total_extractions, total_files_sent)
  - daily_stats : date-wise analytics (active users, extractions)
  - flags : runtime toggles (maintenance_mode)
"""

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

import config

_client = AsyncIOMotorClient(config.MONGO_URI, serverSelectionTimeoutMS=8000)
_db = _client[config.MONGO_DB_NAME]

users_col = _db["users"]
stats_col = _db["stats"]
daily_col = _db["daily_stats"]
flags_col = _db["flags"]


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
    await stats_col.update_one(
        {"_id": "counters"},
        {"$setOnInsert": {"total_extractions": 0, "total_files_sent": 0}},
        upsert=True,
    )
    await flags_col.update_one(
        {"_id": "runtime"},
        {"$setOnInsert": {"maintenance_mode": False}},
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
