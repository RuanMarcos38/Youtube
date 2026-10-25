"""Private source files shared by a user's processing attempts."""
import json
import math
import re
import subprocess
from pathlib import Path

from ..config import settings

MAX_UPLOAD_BYTES = 500 * 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
_REFERENCE = re.compile(r"upload://([a-f0-9]{32})/source\.(mp4|mov|mkv|webm|m4v)\Z")


def source_upload_path(user_id: int, reference: str) -> Path | None:
    if not reference.startswith("upload:"):
        return None
    match = _REFERENCE.fullmatch(reference)
    if not match:
        raise ValueError("Referência de vídeo enviado inválida.")
    root = (settings.data_path / "users" / str(user_id) / "sources").resolve()
    target = (root / match[1] / f"source.{match[2]}").resolve()
    if not target.is_relative_to(root):
        raise ValueError("O arquivo enviado não pertence a este perfil.")
    return target


def inspect_uploaded_video(path: Path) -> int:
    """Validate the actual media, rather than trusting its name or MIME type."""
    try:
        result = subprocess.run(
            [settings.ffprobe_binary, "-v", "error", "-protocol_whitelist", "file,pipe",
             "-format_whitelist", "mov,matroska,webm", "-show_entries",
             "stream=codec_type:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=30,
        )
        info = json.loads(result.stdout)
        kinds = {stream.get("codec_type") for stream in info.get("streams", [])}
        duration = float(info.get("format", {}).get("duration", 0))
    except (subprocess.SubprocessError, OSError, ValueError, TypeError) as exc:
        raise ValueError("Não foi possível ler o vídeo. Envie um arquivo de vídeo válido com áudio.") from exc
    if not {"video", "audio"}.issubset(kinds) or not math.isfinite(duration) or not 1 <= duration <= 86400:
        raise ValueError("Envie um vídeo com imagem e áudio, com duração entre 1 segundo e 24 horas.")
    return math.ceil(duration)
