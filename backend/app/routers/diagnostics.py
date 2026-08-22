from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_superadmin
from ..database import get_db
from ..models import User
from ..services.self_test import run_self_test


router = APIRouter(prefix="/admin/diagnostics", tags=["admin-diagnostics"])


@router.post("/run")
def run_diagnostics(
    auto_fix: bool = True,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Run production checks and apply only safe, reversible repairs.

    The diagnostic must always return a structured result to the assistant UI.
    Long YouTube validation is performed asynchronously by the worker and only
    its cached probe is read here, preventing proxy timeouts and generic 500s.
    """
    try:
        return run_self_test(db, auto_fix=auto_fix)
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "auto_fix": auto_fix,
            "fixes_applied": [],
            "checks": [
                {
                    "name": "Diagnóstico interno",
                    "ok": False,
                    "required": True,
                    "detail": f"O diagnóstico capturou uma exceção sem derrubar o painel: {exc}",
                    "recommendation": "Revisar os logs do serviço shortsia. Nenhuma credencial foi alterada.",
                }
            ],
            "download": {"ok": False, "mode": "unknown", "attempts": 0, "error": "Probe indisponível nesta execução."},
            "summary": "O assistente encontrou uma inconsistência interna, mas o endpoint permaneceu operacional.",
        }
