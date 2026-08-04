"""
security.py
------------
Sab archive-safety logic yahan hai:
  - Path traversal ("zip slip") protection
  - Zip-bomb protection (uncompressed size limit)
  - Password-protected archive detection + extraction
  - Re-zip (extracted files ko wapas ek zip me pack karna)
"""

import os
import shutil
import tarfile
import zipfile
from pathlib import Path

import config

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


def collect_files(root: Path) -> list[Path]:
    """Extracted folder ke andar se saari files (nested folders sahit) list karta hai."""
    return sorted(p for p in root.rglob("*") if p.is_file())


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
