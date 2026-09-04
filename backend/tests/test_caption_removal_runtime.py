from pathlib import Path

from app.services import caption_removal_runtime as runtime
from app.services import editor_ai_pro as pro


def _direct_project(*, action: str = "remove_caption", captions_enabled: bool = False) -> dict:
    return {
        "id": "project-direct",
        "status": "ready",
        "progress": 100,
        "source_clip_id": None,
        "edit_options": {"captions_enabled": captions_enabled},
        "ai_edit_history": [{"action": action}],
        "last_ai_edit_snapshot": {"edit_options": {"captions_enabled": True}},
        "pending_ai_edit": None,
    }


def test_direct_upload_remove_caption_is_queued_for_real_render():
    assert runtime.should_queue_caption_removal(_direct_project()) is True


def test_other_ai_action_is_not_requeued():
    assert runtime.should_queue_caption_removal(_direct_project(action="resize_caption")) is False


def test_project_from_shortsflow_clip_keeps_existing_clean_source_renderer():
    project = _direct_project()
    project["source_clip_id"] = 42
    assert runtime.should_queue_caption_removal(project) is False


def test_pro_renderer_emits_no_generated_text_when_captions_disabled(tmp_path: Path):
    runtime.install_editor_caption_rendering()
    target = tmp_path / "captions-disabled.ass"
    captions = [
        {
            "start": 0.0,
            "end": 2.0,
            "text": "Legenda que não pode aparecer",
            "highlighted_words": [],
        }
    ]
    motion_cues = [
        pro.MotionCue(
            start=0.2,
            end=1.4,
            text="Texto auxiliar que também deve sumir",
            emphasis="impact",
            position="center",
        )
    ]

    pro._write_pro_ass(captions, target, "impact", False, motion_cues)
    content = target.read_text(encoding="utf-8")

    assert "Dialogue:" not in content
    assert "Legenda que não pode aparecer" not in content
    assert "Texto auxiliar que também deve sumir" not in content
