"""
ratelimit.py
------------
Simple in-memory per-user cooldown (spam-protection). Production me multiple
bot instances chalane hain to isse Redis me move kar dena, single-instance
polling bot ke liye in-memory kaafi hai.
"""

import time

import config

_last_action: dict[int, float] = {}


def is_rate_limited(user_id: int) -> tuple[bool, int]:
    """Returns (limited?, seconds_left)."""
    if user_id in config.ADMIN_IDS:
        return False, 0
    now = time.time()
    last = _last_action.get(user_id, 0)
    elapsed = now - last
    if elapsed < config.RATE_LIMIT_SECONDS:
        return True, int(config.RATE_LIMIT_SECONDS - elapsed)
    return False, 0


def mark_action(user_id: int):
    _last_action[user_id] = time.time()
