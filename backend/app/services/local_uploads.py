"""Tenant-scoped, durable input media for jobs created from user uploads.

No arbitrary filesystem paths are ever accepted from HTTP or stored URLs.
"""
from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from ..config import settings
from .editor_ai import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, MAX_UPLOAD_MB

UPLOAD_SCHEME = "shortsflow-upload:"
_UPLOAD_RE = re.compile(r"^shortsflow-upload:([0-9a-f]{32})(\.[a-z0-9]+)$")


def upload_path(user_id: int, upload_id: str, extension: str) -> Path:
    UUID(hex=upload_id)  # Never allow an untrusted path component.
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato de vídeo não permitido.")
    return settings.data_path / "users" / str(int(user_id)) / "uploads" / upload_id / f"source{extension}"


def source_reference(upload_id: str, extension: str) -> str:
    UUID(hex=upload_id)
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato de vídeo não permitido.")
    return f"{UPLOAD_SCHEME}{upload_id}{extension}"


def is_local_source(reference: str) -> bool:
    return str(reference or "").startswith(UPLOAD_SCHEME)


def resolve_local_source(reference: str, user_id: int) -> Path:
    match = _UPLOAD_RE.fullmatch(reference or "")
    if not match:
        raise ValueError("Referência do arquivo enviado inválida.")
    path = upload_path(user_id, match.group(1), match.group(2))
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError("Vídeo enviado não encontrado no armazenamento persistente.")
    return path
