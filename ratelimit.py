"""
ratelimit.py
------------
Per-user cooldown (spam-protection).

Agar config.REDIS_URL set hai to Redis me store hota hai — restart ya
multiple bot instances ke across bhi rate-limit persist rehta hai.
Redis missing/unreachable ho to automatically in-memory fallback (jaisa
pehle tha) use ho jaata hai, taaki bot kabhi crash na ho.
"""

import logging
import time

import config

logger = logging.getLogger(__name__)

_memory_store: dict[int, float] = {}
_redis_client = None
_redis_broken = False  # ek baar fail ho jaye to dobara-dobara retry na kare


def _get_redis():
    """Lazily connect to Redis. Returns client or None (fallback to memory)."""
    global _redis_client, _redis_broken
    if _redis_broken:
        return None
    if _redis_client is not None:
        return _redis_client
    if not config.REDIS_URL:
        return None
    try:
        import redis  # lazy import — redis package sirf tab chahiye jab use ho

        client = redis.from_url(config.REDIS_URL, decode_responses=True, socket_timeout=2)
        client.ping()
        _redis_client = client
        logger.info("Redis rate-limit backend connected.")
        return _redis_client
    except Exception as e:
        logger.warning("Redis unavailable (%s) — using in-memory rate-limit instead.", e)
        _redis_broken = True
        return None


def is_rate_limited(user_id: int, rate_limit_seconds: int | None = None) -> tuple[bool, int]:
    """Returns (limited?, seconds_left). rate_limit_seconds None = config default (backward-compat)."""
    if user_id in config.ADMIN_IDS:
        return False, 0

    limit = config.RATE_LIMIT_SECONDS if rate_limit_seconds is None else rate_limit_seconds
    if limit <= 0:
        return False, 0  # tier has no rate limit (e.g. premium)

    now = time.time()
    r = _get_redis()
    if r is not None:
        try:
            last = r.get(f"ratelimit:{user_id}")
            if last is not None:
                elapsed = now - float(last)
                if elapsed < limit:
                    return True, int(limit - elapsed)
            return False, 0
        except Exception as e:
            logger.warning("Redis read failed (%s), falling back to memory for this check.", e)

    last = _memory_store.get(user_id, 0)
    elapsed = now - last
    if elapsed < limit:
        return True, int(limit - elapsed)
    return False, 0


def mark_action(user_id: int, rate_limit_seconds: int | None = None):
    limit = config.RATE_LIMIT_SECONDS if rate_limit_seconds is None else rate_limit_seconds
    now = time.time()
    r = _get_redis()
    if r is not None:
        try:
            r.set(f"ratelimit:{user_id}", now, ex=max(limit, 1) + 5)
            return
        except Exception as e:
            logger.warning("Redis write failed (%s), falling back to memory.", e)
    _memory_store[user_id] = now
