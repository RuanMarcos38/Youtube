from __future__ import annotations

from . import editor_ai_pro
from .ai_video import run_ai_video_generation
from .editor_audio_mix import mix_sound_design

# Keep the professional editor module cohesive while swapping the FFmpeg 6+
# compatible audio mixer at runtime. Functions defined in editor_ai_pro resolve
# globals from that module, so this assignment is used by enhance_editor_project.
editor_ai_pro._mix_sound_design = mix_sound_design

def run_claimed_editor_task(user_id: int, project_id: str, mode: str) -> None:
    if mode == "ai_video":
        run_ai_video_generation(user_id, project_id)
        return
    editor_ai_pro.run_claimed_editor_task(user_id, project_id, mode)
