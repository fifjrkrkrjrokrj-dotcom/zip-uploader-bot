"""
clamav.py
---------
Virus/malware scanning via ClamAV (clamdscan ya clamscan CLI). Extraction se
PEHLE uploaded archive scan hota hai.

SETUP (server pe):
  sudo apt-get install clamav clamav-daemon
  sudo freshclam            # virus definitions download
  sudo systemctl start clamav-daemon   # clamdscan tab bahut fast hota hai

.env me:
  CLAMAV_ENABLED=true
  CLAMAV_REQUIRED=false     # true = ClamAV missing/down hone par uploads reject
  CLAMAV_SCAN_EXTRACTED=false
"""

import asyncio
import logging
import shutil
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_CLAMSCAN_BIN = shutil.which("clamdscan") or shutil.which("clamscan")


class ScanUnavailable(Exception):
    """ClamAV binary/daemon available nahi hai."""


async def scan_file(path: Path) -> tuple[bool, str]:
    """
    Ek file scan karta hai.
    Returns (is_clean, detail).
    Raises ScanUnavailable agar ClamAV configured/installed nahi hai.
    """
    if not config.CLAMAV_ENABLED:
        return True, "scan disabled"

    if not _CLAMSCAN_BIN:
        raise ScanUnavailable(
            "ClamAV binary (clamdscan/clamscan) is not installed on this system."
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            _CLAMSCAN_BIN,
            "--no-summary",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=config.CLAMAV_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise ScanUnavailable("ClamAV scan timed out.")
    except FileNotFoundError:
        raise ScanUnavailable("ClamAV binary disappeared / not runnable.")

    output = stdout.decode(errors="ignore").strip()

    # clamdscan/clamscan exit codes: 0 = clean, 1 = virus found, 2 = error
    if proc.returncode == 0:
        return True, "clean"
    if proc.returncode == 1:
        return False, output or "malware signature matched"

    raise ScanUnavailable(
        f"ClamAV returned an error (code {proc.returncode}): "
        f"{stderr.decode(errors='ignore').strip() or output}"
    )


async def scan_or_decide(path: Path) -> tuple[bool, str]:
    """
    High-level helper: scan karta hai aur config ke hisaab se decide karta hai
    ki unavailable-scanner ke case me kya karna hai (fail-open vs fail-closed).

    Returns (allowed, message). allowed=False -> caller ko block karna chahiye.
    message khaali string ho sakta hai (no message needed).
    """
    try:
        clean, detail = await scan_file(path)
        if clean:
            return True, ""
        return False, detail
    except ScanUnavailable as e:
        logger.warning("ClamAV unavailable: %s", e)
        if config.CLAMAV_REQUIRED:
            return False, str(e)
        return True, ""  # fail-open: scanner missing but not required
