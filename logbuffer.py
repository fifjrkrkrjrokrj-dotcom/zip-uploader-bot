"""
logbuffer.py
------------
Recent WARNING/ERROR log lines ko ek ring buffer me rakhta hai, taaki admin
/logs command se seedha chat me dekh sake — server SSH me jaake log file
dhoondhne ki zaroorat nahi.
"""

import logging
from collections import deque

_MAX_LOGS = 300
_buffer: deque[str] = deque(maxlen=_MAX_LOGS)


class BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            _buffer.append(self.format(record))
        except Exception:
            pass


def attach(level: int = logging.WARNING):
    """Root logger pe handler attach karta hai. main.py startup me ek baar call karo."""
    handler = BufferHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)


def recent(n: int = 20) -> list[str]:
    return list(_buffer)[-n:]


def clear():
    _buffer.clear()
