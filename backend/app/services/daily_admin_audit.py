from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import SystemSetting
from .self_test import run_self_test


LAST_RUN_KEY = "admin.daily_audit.last_run"
RESULT_KEY = "admin.daily_audit.result"
AUDIT_INTERVAL = timedelta(hours=24)
LOOP_INTERVAL_SECONDS = 60 * 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _setting(db: Session, key: str) -> SystemSetting | None:
    return db.get(SystemSetting, key)


def _save_setting(db: Session, key: str, value: str) -> None:
    row = _setting(db, key)
    if row:
        row.value = value
        row.secret = False
    else:
        db.add(SystemSetting(key=key, value=value, secret=False))


def audit_status(db: Session) -> dict:
    last_row = _setting(db, LAST_RUN_KEY)
    result_row = _setting(db, RESULT_KEY)
    last_run = _parse_datetime(last_row.value if last_row else None)
    result = None
    if result_row and result_row.value:
        try:
            parsed = json.loads(result_row.value)
            if isinstance(parsed, dict):
                result = parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            result = None

    next_due = last_run + AUDIT_INTERVAL if last_run else _utcnow()
    return {
        "last_run": last_run.isoformat() if last_run else None,
        "next_due": next_due.isoformat(),
        "overdue": next_due <= _utcnow(),
        "result": result,
    }


def run_daily_audit_if_due(*, force: bool = False) -> dict:
    db = SessionLocal()
    try:
        status = audit_status(db)
        if not force and not status["overdue"]:
            return status

        started_at = _utcnow()
        try:
            result = run_self_test(db, auto_fix=True)
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            result = {
                "ok": False,
                "auto_fix": True,
                "fixes_applied": [],
                "checks": [
                    {
                        "name": "Varredura diária",
                        "ok": False,
                        "required": True,
                        "detail": f"A varredura capturou uma exceção sem alterar credenciais: {exc}",
                        "recommendation": "Revisar os logs do ShortsFlow. Nenhuma credencial foi modificada.",
                    }
                ],
                "summary": "A varredura diária encontrou uma inconsistência interna e preservou o ambiente atual.",
            }

        finished_at = _utcnow()
        recommendations = [
            str(check.get("recommendation") or "").strip()
            for check in result.get("checks", [])
            if isinstance(check, dict) and not check.get("ok") and str(check.get("recommendation") or "").strip()
        ]
        stored = {
            "ok": bool(result.get("ok")),
            "summary": str(result.get("summary") or ("Tudo operacional." if result.get("ok") else "Há itens para revisar.")),
            "checks": result.get("checks", []),
            "fixes_applied": result.get("fixes_applied", []),
            "recommendations": recommendations[:20],
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
        }
        _save_setting(db, LAST_RUN_KEY, finished_at.isoformat())
        _save_setting(db, RESULT_KEY, json.dumps(stored, ensure_ascii=False, separators=(",", ":")))
        db.commit()
        return audit_status(db)
    finally:
        db.close()


async def daily_admin_audit_loop() -> None:
    # O primeiro ciclo aguarda o serviço estabilizar. Depois a verificação roda
    # em segundo plano e somente executa novamente quando completar 24 horas.
    await asyncio.sleep(45)
    while True:
        try:
            await asyncio.to_thread(run_daily_audit_if_due)
        except asyncio.CancelledError:
            raise
        except Exception:
            # O assistente nunca pode derrubar API, worker ou frontend.
            pass
        await asyncio.sleep(LOOP_INTERVAL_SECONDS)
