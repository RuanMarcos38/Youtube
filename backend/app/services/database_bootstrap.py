from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from ..config import settings
from ..database import Base, engine

logger = logging.getLogger(__name__)

# One-time visual reset requested for the Publications queue. The marker keeps
# the cleanup non-destructive: old clips stay in the database/filesystem, while
# the Publications screen starts clean after this deployment.
PUBLICATIONS_RESET_KEY = "maintenance.publications_clean_start_2026_09_04_v1"

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows/local fallback
    fcntl = None


@contextmanager
def _schema_lock():
    """Serialize SQLite DDL between the API and worker processes.

    Both processes start in the same container. Without a process lock they can
    execute create_all at the same time during a deploy, which can leave the API
    restarting with SQLite 'database is locked' errors while the Next.js frontend
    continues serving the login page.
    """
    if engine.url.get_backend_name() != "sqlite" or fcntl is None:
        yield
        return

    lock_path = settings.data_path / ".schema-init.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def initialize_database(*, attempts: int = 12, delay_seconds: float = 1.0) -> None:
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            with _schema_lock():
                Base.metadata.create_all(bind=engine)
                _ensure_clip_caption_columns()
                _ensure_publications_reset_marker()
            return
        except OperationalError as exc:
            last_error = exc
            logger.warning("Database schema initialization attempt %s failed: %s", attempt, exc)
            if attempt < attempts:
                time.sleep(max(0.1, delay_seconds))

    if last_error:
        raise last_error


def _ensure_clip_caption_columns() -> None:
    inspector = inspect(engine)
    existing = {column["name"] for column in inspector.get_columns("saas_clips")}
    ddl = {
        "caption_position": "caption_position VARCHAR(20) DEFAULT 'bottom' NOT NULL",
        "caption_margin_v": "caption_margin_v INTEGER DEFAULT 120 NOT NULL",
        "caption_font_size": "caption_font_size INTEGER DEFAULT 18 NOT NULL",
    }
    missing = [(column, statement) for column, statement in ddl.items() if column not in existing]
    if not missing:
        return

    clause = "ADD COLUMN" if engine.url.get_backend_name() == "sqlite" else "ADD COLUMN IF NOT EXISTS"
    with engine.begin() as connection:
        for _, statement in missing:
            connection.execute(text(f"ALTER TABLE saas_clips {clause} {statement}"))


def _ensure_publications_reset_marker() -> None:
    """Create one persistent cutoff used to hide legacy queue items.

    This intentionally does not delete clips, jobs, source videos or media files.
    It only records when the Publications queue was reset, so the current
    superadmin workspace can start clean without damaging project history.
    """
    reset_at = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO saas_system_settings (key, value, secret, updated_at)
                VALUES (:key, :value, :secret, :updated_at)
                ON CONFLICT(key) DO NOTHING
                """
            ),
            {
                "key": PUBLICATIONS_RESET_KEY,
                "value": reset_at.isoformat(),
                "secret": False,
                "updated_at": reset_at,
            },
        )
