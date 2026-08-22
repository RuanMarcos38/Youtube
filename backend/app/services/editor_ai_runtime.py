from __future__ import annotations

from . import editor_ai_pro
from .editor_audio_mix import mix_sound_design

# Keep the professional editor module cohesive while swapping the FFmpeg 6+
# compatible audio mixer at runtime. Functions defined in editor_ai_pro resolve
# globals from that module, so this assignment is used by enhance_editor_project.
editor_ai_pro._mix_sound_design = mix_sound_design

run_claimed_editor_task = editor_ai_pro.run_claimed_editor_task
