from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Clip, Job, SourceVideo, Tenant, TikTokPost, User
from app.routers.publications import tiktok_publication_history
from app.services.tiktok_metrics import _alerts, _local_post_summary


def _owner(db, name):
    tenant = Tenant(name=name)
    db.add(tenant)
    db.flush()
    user = User(tenant_id=tenant.id, email=f"{name}@example.com", password_hash="test", display_name=name)
    db.add(user)
    db.flush()
    source = SourceVideo(tenant_id=tenant.id, user_id=user.id, youtube_id=name,
                         title="Source", original_url="https://www.youtube.com/watch?v=test")
    db.add(source)
    db.flush()
    job = Job(tenant_id=tenant.id, user_id=user.id, source_video_id=source.id, status="ready_for_review")
    db.add(job)
    db.flush()
    return user, job


def _post(db, user, job, status, error=None, updated=None):
    clip = Clip(tenant_id=user.tenant_id, user_id=user.id, job_id=job.id,
                start_seconds=0, end_seconds=30, title="Clip", file_path="/not-used.mp4")
    db.add(clip)
    db.flush()
    post = TikTokPost(user_id=user.id, clip_id=clip.id, privacy_level="PUBLIC_TO_EVERYONE",
                      status=status, error=error, updated_at=updated or datetime.now(timezone.utc))
    db.add(post)
    db.flush()
    return post


def test_metrics_show_latest_failure_by_update_and_preserve_user_scope():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        user, job = _owner(db, "owner")
        other, other_job = _owner(db, "other")
        now = datetime.now(timezone.utc)
        _post(db, user, job, "failed", "TikTok bloqueou Direct Post: auditoria pendente", now)
        _post(db, user, job, "failed", "Falha antiga", now - timedelta(days=1))
        _post(db, other, other_job, "failed", "Nao expor outro perfil", now + timedelta(seconds=1))
        db.commit()
        summary = _local_post_summary(db, user.id)
        assert summary["failed"] == 2
        assert summary["latest_failure_message"] == "TikTok bloqueou Direct Post: auditoria pendente"
        alert = next(item for item in _alerts(summary, {}, {}, [], 0) if item["title"] == "Falhas de publicação")
        assert "auditoria pendente" in alert["detail"]
        assert "Nao expor" not in alert["detail"]
    engine.dispose()


def test_recent_failure_on_old_record_is_not_hidden_by_history_limit():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        user, job = _owner(db, "history")
        other, other_job = _owner(db, "foreign")
        now = datetime.now(timezone.utc)
        failed = _post(db, user, job, "failed", "Recusa real do TikTok", now)
        for _ in range(201):
            _post(db, user, job, "ready", updated=now - timedelta(hours=1))
        foreign = _post(db, other, other_job, "failed", "Outro perfil", now + timedelta(seconds=1))
        db.commit()
        history = tiktok_publication_history(user=user, db=db)
        assert len(history) == 200
        assert history[0]["id"] == failed.id
        assert history[0]["error"] == "Recusa real do TikTok"
        assert foreign.id not in {row["id"] for row in history}
        assert db.query(TikTokPost).count() == 203
    engine.dispose()


def test_metrics_keep_fallback_message_when_failure_has_no_detail():
    alerts = _alerts({"failed": 1}, {}, {}, [], 0)
    failure = next(item for item in alerts if item["title"] == "Falhas de publicação")
    assert "Revise os motivos" in failure["detail"]
