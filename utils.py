"""
utils.py
--------
Display/formatting helper functions:
  - human_size(): bytes ko KB/MB/GB me readable banata hai
  - progress_bar(): text-based progress bar banata hai
  - to_small_caps(): UI text ko small-caps style deta hai

(Extraction/security logic ab security.py me hai.)
"""


def human_size(num_bytes: float) -> str:
    """Bytes ko human-readable string me convert karta hai (e.g. 12.4 MB)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def progress_bar(percentage: float, length: int = 12) -> str:
    """Text based progress bar, e.g. [████████░░░░] 65%"""
    filled = int(length * percentage / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {percentage:.0f}%"


def to_small_caps(text: str) -> str:
    """
    Normal text ko Unicode small-caps style me convert karta hai
    (e.g. "Archive Bot" -> "ᴀʀᴄʜɪᴠᴇ ʙᴏᴛ"). Sirf visual style hai,
    numbers/symbols/emoji as-is rehte hain.
    """
    mapping = {
        "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ",
        "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
        "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ",
        "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
        "y": "ʏ", "z": "ᴢ",
    }
    return "".join(mapping.get(ch.lower(), ch) for ch in text)


DIVIDER = "┄" * 22
