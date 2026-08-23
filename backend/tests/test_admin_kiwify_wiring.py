from pathlib import Path


def test_admin_uses_fast_kiwify_connector():
    source = Path("backend/app/routers/admin.py").read_text(encoding="utf-8")
    assert "from ..services.kiwify_fast import register_webhook_fast" in source
    assert "result = register_webhook_fast(" in source
    assert "status_code=400, detail=str(exc)" in source
