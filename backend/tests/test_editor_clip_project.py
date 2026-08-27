import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Clip, Job, SourceVideo, Tenant, User
from app.routers import clips as clips_router
from app.routers import editor_ai as editor_router
from app.services import editor_ai as editor_service


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return session()


def _clip_fixture(db, clip_file):
    tenant = Tenant(name="Editor tenant", billing_status="active")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email="editor@example.com",
        password_hash="hash",
        display_name="Editor user",
        role="owner",
        active=True,
    )
    db.add(user)
    db.flush()
    source = SourceVideo(
        tenant_id=tenant.id,
        user_id=user.id,
        youtube_id="abc123def45",
        title="Original video",
        channel_title="Channel",
        original_url="https://www.youtube.com/watch?v=abc123def45",
        thumbnail_url="https://img.youtube.com/vi/abc123def45/hqdefault.jpg",
        rights_confirmed=True,
    )
    db.add(source)
    db.flush()
    job = Job(
        tenant_id=tenant.id,
        user_id=user.id,
        source_video_id=source.id,
        requested_clips=1,
        status="ready_for_review",
        progress=100,
    )
    db.add(job)
    db.flush()
    subtitle = clip_file.with_suffix(".srt")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:02,000\nTeste\n", encoding="utf-8")
    clip = Clip(
        tenant_id=tenant.id,
        user_id=user.id,
        job_id=job.id,
        start_seconds=10.0,
        end_seconds=42.0,
        hook="Gancho",
        reason="Motivo",
        title="Corte para editar",
        description="Descricao",
        copy_text="CTA",
        tags_json=json.dumps(["shorts", "youtube"]),
        file_path=str(clip_file),
        subtitle_path=str(subtitle),
        caption_position="bottom",
        caption_margin_v=140,
        caption_font_size=20,
        status="ready",
    )
    db.add(clip)
    db.commit()
    return user, clip


def test_create_editor_project_from_clip_reuses_existing_project(tmp_path, monkeypatch):
    monkeypatch.setattr(editor_service.settings, "data_dir", str(tmp_path))
    clip_file = tmp_path / "clip.mp4"
    clip_file.write_bytes(b"fake video bytes")
    db = _session()
    try:
        user, clip = _clip_fixture(db, clip_file)

        created = editor_router.create_project_from_clip(clip.id, user=user, db=db)
        reused = editor_router.create_project_from_clip(clip.id, user=user, db=db)

        project_root = tmp_path / "users" / str(user.id) / "editor-projects" / created["id"]
        assert created["id"] == reused["id"]
        assert created["status"] == "ready"
        assert created["source_clip_id"] == clip.id
        assert created["preview_url"] == f"/api/media/editor-projects/{created['id']}/source.mp4"
        assert created["timeline"]["canvas"]["aspect_ratio"] == "9:16"
        assert created["timeline"]["tracks"][0]["items"][0]["source"] == "source.mp4"
        assert (project_root / "source.mp4").read_bytes() == b"fake video bytes"
        assert len(list((tmp_path / "users" / str(user.id) / "editor-projects").glob("*/project.json"))) == 1
    finally:
        db.close()


def test_ai_edit_plan_moves_caption_to_safe_area(tmp_path, monkeypatch):
    monkeypatch.setattr(editor_service.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(editor_router.settings, "openai_api_key", "")
    clip_file = tmp_path / "clip.mp4"
    clip_file.write_bytes(b"fake video bytes")
    db = _session()
    try:
        user, clip = _clip_fixture(db, clip_file)
        project = editor_router.create_project_from_clip(clip.id, user=user, db=db)

        plan = editor_router.create_ai_edit_plan(
            project["id"],
            editor_router.EditorAiEditRequest(
                prompt="Retire a legenda do rosto da pessoa, mantenha o mesmo texto, a mesma sincronização e o mesmo estilo. Apenas reposicione para uma área segura e legível."
            ),
            user=user,
            db=db,
        )

        stored = editor_service.read_project(user.id, project["id"])
        assert plan.action == "move_caption"
        assert plan.supported is True
        assert plan.caption_position == "bottom"
        assert plan.caption_margin_v == 70
        assert stored["pending_ai_edit"]["action"] == "move_caption"

        remove_plan = editor_router.create_ai_edit_plan(
            project["id"],
            editor_router.EditorAiEditRequest(prompt="Retire as legendas deste vídeo."),
            user=user,
            db=db,
        )
        assert remove_plan.action == "remove_caption"
        assert remove_plan.captions_enabled is False
    finally:
        db.close()


def test_apply_and_undo_ai_caption_edit_reuses_clip_renderer(tmp_path, monkeypatch):
    monkeypatch.setattr(editor_service.settings, "data_dir", str(tmp_path))
    clip_file = tmp_path / "clip.mp4"
    clip_file.write_bytes(b"old rendered clip")
    (tmp_path / "source.mp4").write_bytes(b"original clean source")
    renders = []

    def fake_render(source_path, output_path, start_seconds, end_seconds, subtitle_path, **kwargs):
        renders.append(kwargs)
        output_path.write_bytes(f"rendered-{len(renders)}".encode("utf-8"))
        return output_path

    monkeypatch.setattr(clips_router, "ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(clips_router, "render_vertical_clip", fake_render)
    db = _session()
    try:
        user, clip = _clip_fixture(db, clip_file)
        project = editor_router.create_project_from_clip(clip.id, user=user, db=db)
        project_root = tmp_path / "users" / str(user.id) / "editor-projects" / project["id"]
        plan = editor_router.EditorAiActionPlan(
            action="move_caption",
            supported=True,
            reason="Evitar legenda sobre o rosto.",
            requires_render=True,
            caption_position="bottom",
            caption_margin_v=70,
            caption_font_size=20,
        )

        updated = editor_router.apply_ai_edit_to_project(
            project["id"],
            editor_router.EditorAiApplyRequest(plan=plan),
            user=user,
            db=db,
        )

        assert renders[-1]["caption_margin_v"] == 70
        assert clip.caption_margin_v == 70
        assert (project_root / "source.mp4").read_bytes() == b"rendered-1"
        assert updated["last_ai_edit_snapshot"]["clip"]["caption_margin_v"] == 140
        assert "?v=" in updated["preview_url"]

        undone = editor_router.undo_last_ai_edit(project["id"], user=user, db=db)

        assert renders[-1]["caption_margin_v"] == 140
        assert clip.caption_margin_v == 140
        assert (project_root / "source.mp4").read_bytes() == b"rendered-2"
        assert "last_ai_edit_snapshot" not in undone
    finally:
        db.close()
