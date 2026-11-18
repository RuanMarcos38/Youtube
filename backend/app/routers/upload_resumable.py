"""Upload resumível de vídeos originais, isolado do editor e do download do YouTube.

Cada parte tem no máximo 8 MiB: o proxy não precisa receber a mídia inteira.
O estado é armazenado no mesmo volume persistente dos vídeos processados.
"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import Job, SourceVideo, User
from ..schemas import JobOut
from ..services.billing import can_use_tool
from ..services.editor_ai import ALLOWED_EXTENSIONS
from ..services.ffmpeg_service import get_duration
from ..services.local_uploads import upload_path, source_reference
from .jobs import _create_queued_job, _ensure_job_can_be_queued

router = APIRouter(prefix="/jobs/uploads", tags=["jobs"])
PART_BYTES = 8 * 1024 * 1024
MAX_BYTES = max(1, int(os.getenv("MAX_ORIGINAL_UPLOAD_MB", "5120"))) * 1024 * 1024


class UploadStart(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    size: int = Field(gt=0)
    requested_clips: int = Field(ge=1, le=10)
    rights_confirmed: bool


def _paths(user_id: int, upload_id: str, extension: str) -> tuple[Path, Path, Path]:
    UUID(hex=upload_id)
    target = upload_path(user_id, upload_id, extension)
    return target, target.with_suffix(target.suffix + ".part"), target.parent / "manifest.json"


def _find_upload(user: User, upload_id: str) -> tuple[dict, Path, Path, Path]:
    try:
        UUID(hex=upload_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(404, "Envio não encontrado.") from exc
    root = upload_path(user.id, upload_id, ".mp4").parent
    manifest = root / "manifest.json"
    if not manifest.is_file():
        raise HTTPException(404, "Envio não encontrado.")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data["user_id"] != user.id or data["tenant_id"] != user.tenant_id:
            raise ValueError("owner mismatch")
        target, part, _ = _paths(user.id, upload_id, data["extension"])
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(409, "Metadados do envio inválidos.") from exc
    return data, target, part, manifest


@contextmanager
def _locked(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".upload.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _offset(part: Path) -> int:
    return part.stat().st_size if part.is_file() else 0


@router.post("/init", status_code=201)
def initiate(payload: UploadStart, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.rights_confirmed:
        raise HTTPException(400, "Confirme os direitos de uso do vídeo.")
    if payload.size > MAX_BYTES:
        raise HTTPException(413, "O vídeo excede o limite configurado de envio.")
    extension = Path(payload.name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Formato de vídeo não permitido.")
    allowed, reason = can_use_tool(db, user)
    if not allowed:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, reason)
    upload_id = uuid4().hex
    target, part, manifest = _paths(user.id, upload_id, extension)
    with _locked(target.parent):
        with part.open("xb"):
            pass
        data = {
            "user_id": user.id, "tenant_id": user.tenant_id,
            "name": Path(payload.name).name[:500], "extension": extension,
            "size": payload.size, "requested_clips": payload.requested_clips,
        }
        manifest.write_text(json.dumps(data), encoding="utf-8")
    return {"upload_id": upload_id, "offset": 0, "chunk_size": PART_BYTES}


@router.get("/{upload_id}")
def inspect(upload_id: str, user: User = Depends(get_current_user)):
    data, target, part, _ = _find_upload(user, upload_id)
    return {
        "upload_id": upload_id, "offset": _offset(part),
        "size": data["size"], "name": data["name"],
        "completed": bool(data.get("job_id")),
        "chunk_size": PART_BYTES,
    }


@router.put("/{upload_id}/chunk")
async def receive_chunk(
    upload_id: str, request: Request,
    offset: int = Query(ge=0),
    user: User = Depends(get_current_user),
):
    data, target, part, _ = _find_upload(user, upload_id)
    # Chunked requests intentionally stay below reverse-proxy request limits.
    body = await request.body()
    if not body or len(body) > PART_BYTES:
        raise HTTPException(413, "Parte inválida; envie até 8 MiB por requisição.")
    with _locked(target.parent):
        data, _, part, _ = _find_upload(user, upload_id)
        if data.get("job_id"):
            raise HTTPException(409, "Este envio já foi finalizado.")
        current = _offset(part)
        if offset != current:
            raise HTTPException(409, detail={"expected_offset": current})
        if current + len(body) > data["size"]:
            raise HTTPException(413, "Parte excede o tamanho declarado.")
        with part.open("ab") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        return {"offset": current + len(body), "size": data["size"]}


@router.post("/{upload_id}/finish", response_model=JobOut, status_code=202)
def finish(upload_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data, target, part, manifest = _find_upload(user, upload_id)
    with _locked(target.parent):
        data, target, part, manifest = _find_upload(user, upload_id)
        if data.get("job_id"):
            existing = db.query(Job).options(joinedload(Job.source_video), joinedload(Job.clips)).filter(
                Job.id == data["job_id"], Job.user_id == user.id
            ).first()
            if existing:
                from ..services.serializers import job_to_dict
                return job_to_dict(existing)
            raise HTTPException(409, "Envio já finalizado; processamento indisponível.")
        if _offset(part) != data["size"]:
            raise HTTPException(409, "Envio incompleto. Retome as partes pendentes.")
        try:
            duration = int(get_duration(part))
        except Exception as exc:
            raise HTTPException(415, "Vídeo inválido ou sem mídia decodificável.") from exc
        if duration <= 0 or duration > 86400:
            raise HTTPException(422, "Duração do vídeo inválida.")
        _ensure_job_can_be_queued(user, db, duration, data["requested_clips"], local_upload=True)
        # Persist source media before enqueueing work; never remove it on a retry.
        os.replace(part, target)
        source = SourceVideo(
            tenant_id=user.tenant_id, user_id=user.id,
            youtube_id=upload_id, title=data["name"],
            channel_title="Vídeo original enviado",
            original_url=source_reference(upload_id, data["extension"]),
            thumbnail_url="", duration_seconds=duration, rights_confirmed=True,
        )
        try:
            db.add(source)
            db.flush()
            result = _create_queued_job(db, user, source, data["requested_clips"])
        except Exception:
            db.rollback()
            # Keep target so retry can be diagnosed/recovered; never delete user media.
            raise
        data["job_id"] = result["id"]
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return result
