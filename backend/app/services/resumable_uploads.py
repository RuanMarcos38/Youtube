"""Persistent, per-user upload state stored beside the original video files."""
import json
import os
import shutil
import time
from contextlib import contextmanager

from fastapi import HTTPException

from ..config import settings

try:
    import fcntl
except ImportError:
    import msvcrt
    fcntl = None

CHUNK_BYTES = 8 * 1024**2
MAX_RESUMABLE_BYTES = 5 * 1024**3
DISK_RESERVE_BYTES = 12 * 1024**3  # Worker makes a private copy and generates media.
SESSION_TTL = 24 * 60 * 60


@contextmanager
def locked_upload(user_id):
    root = settings.data_path / "users" / str(user_id) / "upload-session"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (root / "lock").open("a+b") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        else:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield root
        finally:
            if fcntl:
                fcntl.flock(lock, fcntl.LOCK_UN)
            else:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def read_session(root):
    try:
        return json.loads((root / "session.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def write_session(root, session):
    temp = root / "session.tmp"
    temp.write_text(json.dumps(session), encoding="utf-8")
    temp.replace(root / "session.json")


def get_session(root, token):
    session = read_session(root)
    if not session or session["id"] != token or session["expires"] <= time.time():
        raise HTTPException(404, "Envio expirado ou inexistente. Selecione o vídeo novamente.")
    return session


def check_space(root, required):
    if shutil.disk_usage(root).free < DISK_RESERVE_BYTES + required:
        raise HTTPException(507, "Espaço temporariamente insuficiente para enviar e processar o vídeo.")


def append_chunk(root, session, offset, data):
    if offset != session["offset"]:
        raise HTTPException(409, "O envio avançou. Consulte o progresso e tente novamente.")
    if len(data) != min(CHUNK_BYTES, session["size"] - offset) or not data:
        raise HTTPException(400, "Tamanho da parte inválido.")
    check_space(root, len(data))
    with (root / "video.part").open("r+b") as video:
        video.seek(offset)
        video.write(data)
        video.truncate()
        video.flush()
        os.fsync(video.fileno())
    session.update(offset=offset + len(data), expires=time.time() + SESSION_TTL)
    write_session(root, session)


def discard_expired_uploads():
    now = time.time()
    for root in (settings.data_path / "users").glob("*/upload-session"):
        session = read_session(root)
        if not session or session["expires"] > now:
            continue
        with locked_upload(root.parent.name):
            session = read_session(root)
            if session and session["expires"] <= now:
                (root / "video.part").unlink(missing_ok=True)
                (root / "session.json").unlink(missing_ok=True)
