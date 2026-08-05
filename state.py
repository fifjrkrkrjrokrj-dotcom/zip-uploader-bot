"""
state.py
--------
Pyrogram me python-telegram-bot ke `context.user_data` jaisa built-in
per-user scratch-space nahi hota — isliye ye ek simple process-memory dict
hai jo wahi kaam karta hai (admin ke "awaiting_ban_id" jaise multi-step
flows track karne ke liye). Restart pe reset ho jaata hai, jo theek hai
kyunki ye sirf short-lived UI-flow state hai, permanent data nahi.
"""

USER_DATA: dict[int, dict] = {}


def get_user_data(user_id: int) -> dict:
    return USER_DATA.setdefault(user_id, {})
