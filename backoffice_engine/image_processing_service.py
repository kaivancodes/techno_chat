"""
image_processing_service.py
───────────────────────────
Shared image helpers for chat upload and generation flows.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from uuid import uuid4

from django.conf import settings


def save_uploaded_image(uploaded_file, subdir: str = "chat_inputs") -> str:
    extension = Path(uploaded_file.name or "").suffix.lower() or ".png"
    filename = f"{uuid4().hex}{extension}"
    target_dir = Path(settings.MEDIA_ROOT) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    with open(target_path, "wb+") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)

    return os.path.join(settings.MEDIA_URL, subdir, filename).replace("\\", "/")


def uploaded_image_to_data_uri(uploaded_file) -> str:
    content_type = getattr(uploaded_file, "content_type", "") or "image/png"
    uploaded_file.seek(0)          # always reset to start before reading
    file_bytes = uploaded_file.read()
    uploaded_file.seek(0)          # reset again for any downstream consumers
    encoded = base64.b64encode(file_bytes).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"
