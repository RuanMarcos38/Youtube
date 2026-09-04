from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from . import editor_ai as base
from . import editor_ai_pro as pro


_RENDER_PATCHED = False
_API_PATCHED = False


def _captions_enabled_from_payload(project: dict[str, Any]) -> bool:
    options = project.get("edit_options") or {}
    return bool(options.get("captions_enabled", True))


def _captions_enabled_from_project_dir(root: Path) -> bool:
    project_file = root / "project.json"
    if not project_file.is_file():
        return True
    try:
        payload = json.loads(project_file.read_text(encoding="utf-8"))
    except Exception:
        return True
    return _captions_enabled_from_payload(payload)


def should_queue_caption_removal(project: dict[str, Any]) -> bool:
    """Return True only after a direct-upload remove-caption action was applied.

    Projects created from a ShortsFlow Clip already have a dedicated clean-source
    renderer in routers/clips.py and must keep that existing synchronous path.
    Direct uploads, however, need the Editor worker to recreate the preview.
    """
    if project.get("source_clip_id") or (project.get("loaded_from_clip") or {}).get("clip_id"):
        return False
    if project.get("pending_ai_edit"):
        return False
    if project.get("status") != "ready":
        return False
    if _captions_enabled_from_payload(project):
        return False
    if not isinstance(project.get("last_ai_edit_snapshot"), dict):
        return False

    history = project.get("ai_edit_history") or []
    if not history or not isinstance(history[-1], dict):
        return False
    return str(history[-1].get("action") or "") == "remove_caption"


def install_editor_api_caption_queue(editor_router_module: Any) -> None:
    """Make the existing AI apply endpoint queue a real render for direct uploads.

    This patches only the imported save_project reference used by the editor
    router. The underlying project storage service and every other route remain
    unchanged.
    """
    global _API_PATCHED
    if _API_PATCHED:
        return

    original_save = editor_router_module.save_project
    if getattr(original_save, "_shortsflow_caption_queue_patch", False):
        _API_PATCHED = True
        return

    def save_project_caption_aware(user_id: int, project_id: str, payload: dict[str, Any]):
        if should_queue_caption_removal(payload):
            payload = dict(payload)
            payload["status"] = "queued"
            payload["progress"] = 70
            payload["error"] = None
            payload["caption_removal_pending"] = True
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        return original_save(user_id, project_id, payload)

    setattr(save_project_caption_aware, "_shortsflow_caption_queue_patch", True)
    editor_router_module.save_project = save_project_caption_aware
    _API_PATCHED = True


def install_editor_caption_rendering() -> None:
    """Honor captions_enabled=False in both base and professional renders.

    Base editor previously always burned its generated ASS file into preview.mp4.
    Professional editor also kept motion-cue text even when captions were disabled.
    The wrappers below change only the text layer; video cuts, effects, audio,
    framing and project structure continue through the existing render functions.
    """
    global _RENDER_PATCHED
    if _RENDER_PATCHED:
        return

    original_render_timeline = base._render_timeline
    if not getattr(original_render_timeline, "_shortsflow_caption_render_patch", False):
        def render_timeline_caption_aware(
            source: Path,
            output: Path,
            keep_ranges: list[tuple[float, float]],
            ass_path: Path,
        ) -> None:
            if _captions_enabled_from_project_dir(ass_path.parent):
                return original_render_timeline(source, output, keep_ranges, ass_path)

            # Keep the exact existing renderer and filters, replacing only its
            # subtitle input by an ASS file with no Dialogue events.
            clean_ass = ass_path.parent / "captions-disabled.ass"
            base._write_ass([], clean_ass, "impact")
            return original_render_timeline(source, output, keep_ranges, clean_ass)

        setattr(render_timeline_caption_aware, "_shortsflow_caption_render_patch", True)
        base._render_timeline = render_timeline_caption_aware

    original_write_pro_ass = pro._write_pro_ass
    if not getattr(original_write_pro_ass, "_shortsflow_caption_render_patch", False):
        def write_pro_ass_caption_aware(
            captions: list[dict[str, Any]],
            output_path: Path,
            style: str,
            enabled: bool = True,
            motion_cues=None,
        ) -> Path:
            if not enabled:
                # Motion cues in this ASS are textual callouts as well. When the
                # user requests a clean video, suppress every generated text item.
                return original_write_pro_ass([], output_path, style, False, [])
            return original_write_pro_ass(captions, output_path, style, True, motion_cues)

        setattr(write_pro_ass_caption_aware, "_shortsflow_caption_render_patch", True)
        pro._write_pro_ass = write_pro_ass_caption_aware

    _RENDER_PATCHED = True


def _cache_bust_clean_preview(user_id: int, project_id: str) -> None:
    project = base.read_project(user_id, project_id)
    if not project.get("caption_removal_pending"):
        return
    if project.get("status") != "ready":
        return
    if _captions_enabled_from_payload(project):
        return

    project.pop("caption_removal_pending", None)
    preview_url = str(project.get("preview_url") or "")
    if preview_url:
        clean_url = preview_url.split("?", 1)[0]
        version = int(datetime.now(timezone.utc).timestamp() * 1000)
        project["preview_url"] = f"{clean_url}?v={version}"

    analysis = dict(project.get("analysis") or {})
    captions = dict(analysis.get("captions") or {})
    captions["enabled"] = False
    analysis["captions"] = captions
    project["analysis"] = analysis

    # The rendered video is now clean. Keeping an empty caption track prevents
    # old editor metadata from suggesting that text is still active.
    timeline = project.get("timeline") or {}
    for track in timeline.get("tracks") or []:
        if track.get("type") == "captions":
            track["items"] = []
    project["timeline"] = timeline
    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    base.save_project(user_id, project_id, project)


def run_caption_aware_editor_task(user_id: int, project_id: str, mode: str) -> None:
    install_editor_caption_rendering()
    pro.run_claimed_editor_task(user_id, project_id, mode)
    if mode != "export":
        _cache_bust_clean_preview(user_id, project_id)
