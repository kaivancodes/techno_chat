"""
helpers.py
──────────
Small utility functions used across the app.
"""

import re
import functools
import time

import fitz

from backoffice_engine.choices import FileType
from backoffice_engine.constants import (
    MAX_RETRY_ATTEMPTS,
    NETWORK_EXCEPTION_TYPES,
    NETWORK_SIGNALS,
    QUOTA_SIGNALS,
    RETRY_BACKOFF_BASE,
)
from backoffice_engine.models import User, UserProfile
from techno_chat.settings import logger


def detect_file_type(file_name: str):
    """
    Map a filename extension to its FileType enum value.
    Returns None if the extension is not supported.
    """
    ext = file_name.lower().split(".")[-1]

    image_types = ["png", "jpg", "jpeg", "webp", "svg"]
    pdf_types   = ["pdf"]
    doc_types   = ["doc", "docx"]
    excel_types = ["xls", "xlsx"]
    power_types = ["ppt", "pptx"]
    txt_types   = ["txt"]
    csv_types   = ["csv"]
    md_types    = ["md"]

    if ext in image_types:
        return FileType.IMAGE
    if ext in pdf_types:
        return FileType.PDF
    if ext in doc_types:
        return FileType.DOC
    if ext in excel_types:
        return FileType.EXCEL
    if ext in power_types:
        return FileType.POWER
    if ext in txt_types:
        return FileType.TXT
    if ext in csv_types:
        return FileType.CSV
    if ext in md_types:
        return FileType.MD

    return None


def normalize_file_type(file_type: str, file_name: str = "") -> str:
    """
    Normalize stored broad file categories to concrete content types where helpful.
    """
    lowered = (file_type or "").strip().lower()
    extension = file_name.lower().split(".")[-1] if "." in file_name else ""

    if lowered == FileType.POWER:
        return "pptx" if extension == "pptx" else "ppt"
    if lowered == FileType.EXCEL:
        return "xlsx" if extension in {"xlsx", "xls"} else "xlsx"
    if lowered == FileType.DOC:
        return "docx" if extension in {"docx", "doc"} else "docx"
    if lowered == FileType.IMAGE and extension in {"png", "jpg", "jpeg", "webp", "svg"}:
        return extension
    return lowered or extension


def sanitise_filename(name: str) -> str:
    """
    Convert an original filename into a safe Pinecone vector ID component.
    "Attention is All You Need.pdf"  →  "attention_is_all_you_need_pdf"
    """
    name = name.lower()
    name = name.replace(".", "_")
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    return name[:80]


def normalise_image(image_bytes: bytes, ext: str) -> tuple[bytes, str]:
    """
    Convert any unsupported format (jpx, jb2, cmyk, …) to PNG using PyMuPDF.
    Returns (bytes, extension) always in a Gemini-safe format.
    """
    supported = {"jpeg", "jpg", "png", "webp"}
    ext = ext.lower().lstrip(".")
    if ext in supported:
        return image_bytes, ext
    try:
        pix = fitz.Pixmap(image_bytes)
        if pix.n > 4:                          # CMYK → RGB
            pix = fitz.Pixmap(fitz.csRGB, pix)
        return pix.tobytes("png"), "png"
    except Exception:
        return image_bytes, ext                # best-effort fallback


def extract_md_section_name(section_text: str, fallback: str) -> str:
    """Return the first heading's text, or fallback if none found."""
    for line in section_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            name = re.sub(r"^#+\s*", "", stripped).strip()
            return name if name else fallback
    return fallback


# ═════════════════════════════════════════════════════════════════════════════
# AUTH HELPER
# ═════════════════════════════════════════════════════════════════════════════

def _get_user(request):
    """Get current user from session or return None."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        request.session.flush()
        return None

def _get_or_create_profile(user):
    """Return (or create) the UserProfile for *user*."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile

def _nav_context(user):
    """
    Build the three template variables base.html needs for the
    avatar / dropdown.  Spread with ** into every render() call.
    """
    profile = _get_or_create_profile(user)
    return {
        "initials":         profile.get_initials(),
        "display_name":     profile.get_display_name(),
        "username_display": (
            f"@{profile.username}"
            if profile.username
            else f"@{user.email.split('@')[0]}"
        ),
    }


def attach_user_file_display_ids(files):
    """
    Add a user-scoped display id without touching the database primary key.
    """
    ordered_ids = []
    if files:
        first_file = files.first()
        if first_file is not None:
            queryset = files.model.objects.filter(user=first_file.user).order_by("created_at", "id")
            ordered_ids = list(queryset.values_list("id", flat=True))

    id_map = {}
    for index, file_id in enumerate(ordered_ids, start=1):
        id_map[file_id] = index

    for file_obj in files:
        file_obj.display_file_id = id_map.get(file_obj.id, file_obj.id)
    return files

def is_network_error(e):
    if isinstance(e, NETWORK_EXCEPTION_TYPES):
        return True
    return any(sig in str(e).lower() for sig in NETWORK_SIGNALS)

def is_quota_error(e):
    return any(sig in str(e).lower() for sig in QUOTA_SIGNALS)

def retry_on_network(max_attempts=None, backoff_base=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _max = max_attempts or MAX_RETRY_ATTEMPTS
            _base = backoff_base or RETRY_BACKOFF_BASE

            for attempt in range(1, _max + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if is_network_error(e) and attempt < _max:
                        wait = _base * (2 ** (attempt - 1))
                        logger.warning(
                            "Network retry | func=%s | attempt=%s/%s | wait=%s | err=%s",
                            func.__name__, attempt, _max, wait, e
                        )
                        time.sleep(wait)
                        continue
                    raise e
        return wrapper
    return decorator
