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

    This endpoint deliberately does not mutate Google OAuth publication status,
    invent proxy credentials, rotate secrets or requeue jobs automatically.
    External account verification and IP-reputation failures are reported with
    the exact remediation required.
    """
    return run_self_test(db, auto_fix=auto_fix)
