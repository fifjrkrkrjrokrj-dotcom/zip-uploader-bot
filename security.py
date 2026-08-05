"""
security.py
------------
Sab archive-safety logic yahan hai:
  - Path traversal ("zip slip") protection
  - Zip-bomb protection (uncompressed size limit)
  - Password-protected archive detection + extraction
  - Content listing WITHOUT extracting (real preview-before-extract)
  - Nested archive auto-extraction (zip ke andar zip/rar/7z/tar)
  - File-type blacklist filtering (.exe/.bat/etc skip)
  - Re-zip (extracted files ko wapas ek zip me pack karna)
"""

import logging
import os
import shutil
import tarfile
import zipfile
from pathlib import Path

import config

logger = logging.getLogger(__name__)

try:
    import rarfile
    RAR_SUPPORTED = True
except ImportError:
    RAR_SUPPORTED = False

try:
    import py7zr
    SEVEN_ZIP_SUPPORTED = True
except ImportError:
    SEVEN_ZIP_SUPPORTED = False


class UnsupportedArchiveError(Exception):
    pass


class PasswordRequiredError(Exception):
    """Archive encrypted hai — password chahiye."""
    pass


class WrongPasswordError(Exception):
    pass


class ArchiveTooLargeError(Exception):
    """Zip-bomb protection triggered."""
    pass


class UnsafePathError(Exception):
    """Zip-slip / path traversal attempt detected."""
    pass


def _is_within_directory(directory: Path, target: Path) -> bool:
    directory = directory.resolve()
    target = target.resolve()
    return directory == target or directory in target.parents


def _safe_member_check(extract_to: Path, member_name: str):
    """Har member ka resolved path extract_to ke andar hi hona chahiye."""
    target_path = extract_to / member_name
    if not _is_within_directory(extract_to, target_path):
        raise UnsafePathError(f"Unsafe path in archive: {member_name}")


def _check_zip_size(zf: zipfile.ZipFile):
    total = sum(i.file_size for i in zf.infolist())
    limit = config.MAX_EXTRACTED_SIZE_MB * 1024 * 1024
    if total > limit:
        raise ArchiveTooLargeError(
            f"Extracted size ({total / (1024*1024):.0f} MB) limit "
            f"({config.MAX_EXTRACTED_SIZE_MB} MB) se zyada hai."
        )


def _check_tar_size(tf: tarfile.TarFile):
    total = sum(m.size for m in tf.getmembers() if m.isfile())
    limit = config.MAX_EXTRACTED_SIZE_MB * 1024 * 1024
    if total > limit:
        raise ArchiveTooLargeError(
            f"Extracted size ({total / (1024*1024):.0f} MB) limit "
            f"({config.MAX_EXTRACTED_SIZE_MB} MB) se zyada hai."
        )


def is_archive(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(config.SUPPORTED_EXTENSIONS):
        return True
    try:
        return zipfile.is_zipfile(path) or tarfile.is_tarfile(path)
    except Exception:
        return False


def needs_password(archive_path: Path) -> bool:
    """Archive encrypted hai ya nahi, bina password ke check karta hai."""
    name = archive_path.name.lower()
    try:
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as zf:
                return any(i.flag_bits & 0x1 for i in zf.infolist())
        if name.endswith(".rar") and RAR_SUPPORTED:
            with rarfile.RarFile(archive_path) as rf:
                return rf.needs_password()
        if name.endswith(".7z") and SEVEN_ZIP_SUPPORTED:
            with py7zr.SevenZipFile(archive_path, mode="r") as sz:
                return sz.needs_password()
    except Exception:
        return False
    return False


# ============================================================
#  PREVIEW — list contents WITHOUT extracting
# ============================================================
def list_archive_contents(archive_path: Path, password: str | None = None) -> list[tuple[str, int]]:
    """
    Archive ke andar ki files [(name, size_bytes), ...] list karta hai —
    bina kuch disk pe extract kiye. Preview-before-extract ke liye use hota hai.

    Raises PasswordRequiredError / WrongPasswordError / UnsupportedArchiveError
    jaisa extract_archive() karta hai.
    """
    name = archive_path.name.lower()

    if zipfile.is_zipfile(archive_path):
        try:
            with zipfile.ZipFile(archive_path) as zf:
                if password:
                    zf.setpassword(password.encode())
                return [(i.filename, i.file_size) for i in zf.infolist() if not i.is_dir()]
        except RuntimeError as e:
            if "password" in str(e).lower():
                raise (WrongPasswordError(str(e)) if password else PasswordRequiredError(str(e)))
            raise

    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as tf:
            return [(m.name, m.size) for m in tf.getmembers() if m.isfile()]

    if name.endswith(".rar"):
        if not RAR_SUPPORTED:
            raise UnsupportedArchiveError(
                "RAR support install nahi hai. Server pe 'pip install rarfile' "
                "aur 'unrar' (ya 'unar') binary install karo."
            )
        try:
            with rarfile.RarFile(archive_path) as rf:
                if rf.needs_password() and not password:
                    raise PasswordRequiredError("RAR archive password-protected hai.")
                if password:
                    rf.setpassword(password)
                return [(i.filename, i.file_size) for i in rf.infolist() if not i.isdir()]
        except rarfile.RarWrongPassword:
            raise WrongPasswordError("Galat password.")

    if name.endswith(".7z"):
        if not SEVEN_ZIP_SUPPORTED:
            raise UnsupportedArchiveError("7z support install nahi hai. Server pe 'pip install py7zr' karo.")
        try:
            with py7zr.SevenZipFile(archive_path, mode="r", password=password) as sz:
                if sz.needs_password() and not password:
                    raise PasswordRequiredError("7z archive password-protected hai.")
                try:
                    # py7zr >= 0.20: list() returns FileInfo-like objects with
                    # filename / uncompressed / is_directory attributes.
                    return [
                        (info.filename, getattr(info, "uncompressed", 0))
                        for info in sz.list()
                        if not getattr(info, "is_directory", False)
                    ]
                except AttributeError:
                    # Older/alternate py7zr API fallback — names only, no per-file size.
                    return [(n, 0) for n in sz.getnames()]
        except py7zr.exceptions.PasswordRequired:
            raise PasswordRequiredError("7z archive password-protected hai.")
        except py7zr.exceptions.Bad7zFile:
            raise WrongPasswordError("Galat password ya corrupt file.")

    raise UnsupportedArchiveError(
        "Ye file format extract nahi ho saka. Sirf ZIP, RAR, 7Z, TAR supported hain."
    )


# ============================================================
#  EXTRACTION
# ============================================================
def extract_archive(archive_path: Path, extract_to: Path, password: str | None = None) -> None:
    """
    Archive ko safely extract karta hai:
      - Zip-slip protection (path traversal)
      - Zip-bomb protection (size limit)
      - Password support (zip / rar / 7z)
    """
    extract_to.mkdir(parents=True, exist_ok=True)
    name = archive_path.name.lower()

    # --- ZIP ---
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as zf:
            _check_zip_size(zf)
            for info in zf.infolist():
                _safe_member_check(extract_to, info.filename)
            try:
                pwd = password.encode() if password else None
                zf.extractall(extract_to, pwd=pwd)
            except RuntimeError as e:
                if "password" in str(e).lower():
                    raise (WrongPasswordError(str(e)) if password else PasswordRequiredError(str(e)))
                raise
        return

    # --- TAR (.tar, .tar.gz, .tar.bz2) ---
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as tf:
            _check_tar_size(tf)
            for member in tf.getmembers():
                _safe_member_check(extract_to, member.name)
            tf.extractall(extract_to)
        return

    # --- RAR ---
    if name.endswith(".rar"):
        if not RAR_SUPPORTED:
            raise UnsupportedArchiveError(
                "RAR support install nahi hai. Server pe 'pip install rarfile' "
                "aur 'unrar' (ya 'unar') binary install karo."
            )
        try:
            with rarfile.RarFile(archive_path) as rf:
                if rf.needs_password() and not password:
                    raise PasswordRequiredError("RAR archive password-protected hai.")
                total = sum(i.file_size for i in rf.infolist())
                if total > config.MAX_EXTRACTED_SIZE_MB * 1024 * 1024:
                    raise ArchiveTooLargeError(
                        f"Extracted size limit ({config.MAX_EXTRACTED_SIZE_MB} MB) se zyada hai."
                    )
                for info in rf.infolist():
                    _safe_member_check(extract_to, info.filename)
                rf.extractall(extract_to, pwd=password)
        except rarfile.RarWrongPassword:
            raise WrongPasswordError("Galat password.")
        return

    # --- 7Z ---
    if name.endswith(".7z"):
        if not SEVEN_ZIP_SUPPORTED:
            raise UnsupportedArchiveError(
                "7z support install nahi hai. Server pe 'pip install py7zr' karo."
            )
        try:
            with py7zr.SevenZipFile(archive_path, mode="r", password=password) as sz:
                if sz.needs_password() and not password:
                    raise PasswordRequiredError("7z archive password-protected hai.")
                info = sz.archiveinfo()
                if info.uncompressed > config.MAX_EXTRACTED_SIZE_MB * 1024 * 1024:
                    raise ArchiveTooLargeError(
                        f"Extracted size limit ({config.MAX_EXTRACTED_SIZE_MB} MB) se zyada hai."
                    )
                for name_in_archive in sz.getnames():
                    _safe_member_check(extract_to, name_in_archive)
                sz.extractall(path=extract_to)
        except py7zr.exceptions.PasswordRequired:
            raise PasswordRequiredError("7z archive password-protected hai.")
        except py7zr.exceptions.Bad7zFile:
            raise WrongPasswordError("Galat password ya corrupt file.")
        return

    raise UnsupportedArchiveError(
        "Ye file format extract nahi ho saka. Sirf ZIP, RAR, 7Z, TAR supported hain."
    )


# ============================================================
#  NESTED ARCHIVES — zip ke andar zip auto-extract
# ============================================================
def auto_extract_nested(extract_dir: Path, max_depth: int = None, max_archives: int = None) -> int:
    """
    extract_dir ke andar agar koi aur archive files mile (.zip/.rar/.7z/.tar)
    to unhe bhi extract karta hai, un-hi ka folder bana ke (nested archive ka
    naam minus extension), aur andar-nested archives ko bhi recursively
    (max_depth tak) extract karta hai. Har nested extraction pe wahi
    zip-bomb/path-traversal safety checks lagti hain jo top-level pe lagti hain.

    Returns: total nested archives jo extract hui.
    """
    max_depth = config.MAX_NESTED_DEPTH if max_depth is None else max_depth
    max_archives = config.MAX_NESTED_ARCHIVES if max_archives is None else max_archives

    extracted_count = 0

    def _walk_and_extract(base: Path, depth: int):
        nonlocal extracted_count
        if depth > max_depth or extracted_count >= max_archives:
            return

        # Snapshot pehle se, kyunki extraction naye files add karega jinhe
        # is pass me dobara process nahi karna (wo agle depth pass me honge).
        candidates = [
            p for p in base.rglob("*")
            if p.is_file() and p.name.lower().endswith(config.SUPPORTED_EXTENSIONS)
        ]

        for nested_path in candidates:
            if extracted_count >= max_archives:
                break
            try:
                if needs_password(nested_path):
                    # Nested encrypted archive ke liye interactively password
                    # maangna practical nahi — usse as-is chhod dete hain.
                    logger.info("Skipping password-protected nested archive: %s", nested_path)
                    continue

                nested_extract_dir = nested_path.parent / f"{nested_path.stem}_extracted"
                nested_extract_dir.mkdir(parents=True, exist_ok=True)
                extract_archive(nested_path, nested_extract_dir, password=None)
                nested_path.unlink(missing_ok=True)  # nested archive delete, sirf contents rakho
                extracted_count += 1
            except (UnsupportedArchiveError, ArchiveTooLargeError, UnsafePathError) as e:
                logger.info("Nested archive skipped (%s): %s", nested_path, e)
            except Exception:
                logger.exception("Nested extraction failed for %s", nested_path)

        if candidates and extracted_count < max_archives:
            _walk_and_extract(base, depth + 1)

    _walk_and_extract(extract_dir, depth=1)
    return extracted_count


# ============================================================
#  COLLECTION / FILTERING / RE-ZIP
# ============================================================
def collect_files(root: Path) -> list[Path]:
    """Extracted folder ke andar se saari files (nested folders sahit) list karta hai."""
    return sorted(p for p in root.rglob("*") if p.is_file())


def filter_blacklist(files: list[Path]) -> tuple[list[Path], list[Path]]:
    """
    Blacklisted extensions (.exe/.bat/etc, config.BLACKLIST_EXTENSIONS) wali
    files ko alag karta hai. Returns (allowed_files, blocked_files).
    """
    allowed, blocked = [], []
    for f in files:
        if f.suffix.lower() in config.BLACKLIST_EXTENSIONS:
            blocked.append(f)
        else:
            allowed.append(f)
    return allowed, blocked


def rezip_files(file_paths: list[Path], base_dir: Path, output_zip_path: Path) -> Path:
    """Extracted files ko wapas ek single zip me pack karta hai (relative paths preserve karke)."""
    output_zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            zf.write(fp, arcname=str(fp.relative_to(base_dir)))
    return output_zip_path


def cleanup(*paths: Path):
    """Diye gaye files/folders ko safely delete karta hai."""
    for p in paths:
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        except Exception:
            pass
