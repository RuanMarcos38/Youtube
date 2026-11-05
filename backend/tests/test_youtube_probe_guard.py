from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
import pytest
from app.routers import jobs as jobs_router


def _probe(age_minutes: int, *, ok=False, kind="youtube_ip_challenge"):
    return {"checked_at": (datetime.now(timezone.utc) - timedelta(minutes=age_minutes)).isoformat(),
            "ok": ok, "failure_kind": kind}


@pytest.mark.parametrize("age,kind,should_block", [
    (1, "youtube_ip_challenge", True),
    (19, "youtube_ip_challenge", True),
    (21, "youtube_ip_challenge", False),
    (1, "network_unreachable", False),
    (1, "unknown", False),
])
def test_fresh_external_challenge_guard(monkeypatch, age, kind, should_block):
    monkeypatch.setattr(jobs_router, "read_download_probe", lambda: _probe(age, kind=kind))
    assert jobs_router._youtube_probe_blocked() is should_block


def test_invalid_or_missing_probe_does_not_claim_blockage(monkeypatch):
    for value in (None, {}, {"checked_at": "invalid", "ok": False, "failure_kind": "youtube_ip_challenge"}):
        monkeypatch.setattr(jobs_router, "read_download_probe", lambda value=value: value)
        assert not jobs_router._youtube_probe_blocked()


def test_local_uploaded_job_is_not_blocked(monkeypatch):
    monkeypatch.setattr(jobs_router, "read_download_probe", lambda: _probe(1))
    monkeypatch.setattr(jobs_router.settings, "environment", "production")
    monkeypatch.setattr(jobs_router, "can_use_tool", lambda db, user: (True, ""))
    user = type("FakeUser", (), {"role": "superadmin"})()
    jobs_router._ensure_job_can_be_queued(user, None, 120, 3, local_upload=True)
    with pytest.raises(HTTPException) as error:
        jobs_router._ensure_job_can_be_queued(user, None, 120, 3)
    assert error.value.status_code == 503
    assert "Nenhum processamento" in error.value.detail
