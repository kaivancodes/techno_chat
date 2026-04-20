"""
image_processing_service.py
───────────────────────────
Shared image helpers for chat upload and generation flows.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
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


def save_generated_image(image_reference: str, subdir: str = "page_renders") -> tuple[str, str]:
    target_dir = Path(settings.MEDIA_ROOT) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    if image_reference.startswith("data:image/"):
        header, encoded = image_reference.split(",", 1)
        mime = header.split(";")[0].split(":", 1)[1]
        extension = "." + (mime.split("/", 1)[1] or "png")
        file_bytes = base64.b64decode(encoded)
    else:
        parsed = urlsplit(image_reference)
        extension = Path(parsed.path).suffix.lower() or ".png"
        request = Request(image_reference, headers={"User-Agent": "TechnoChat/1.0"})
        with urlopen(request, timeout=60) as response:
            file_bytes = response.read()
            content_type = response.headers.get_content_type() if response.headers else ""
            if not Path(parsed.path).suffix and "/" in content_type:
                extension = "." + content_type.split("/", 1)[1]

    filename = f"{uuid4().hex}{extension}"
    target_path = target_dir / filename
    with open(target_path, "wb") as destination:
        destination.write(file_bytes)

    media_url = os.path.join(settings.MEDIA_URL, subdir, filename).replace("\\", "/")
    return media_url, str(target_path)
