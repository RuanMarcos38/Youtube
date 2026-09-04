from __future__ import annotations

from . import editor_ai_pro
from .caption_removal_runtime import install_editor_caption_rendering, run_caption_aware_editor_task
from .editor_audio_mix import mix_sound_design

# Keep the professional editor module cohesive while swapping the FFmpeg 6+
# compatible audio mixer at runtime. Functions defined in editor_ai_pro resolve
# globals from that module, so this assignment is used by enhance_editor_project.
editor_ai_pro._mix_sound_design = mix_sound_design

# Honor captions_enabled=False in both the base and professional renderers.
# Every existing video/audio/effect path is preserved; only generated text is
# omitted when the user explicitly requests a clean video.
install_editor_caption_rendering()

run_claimed_editor_task = run_caption_aware_editor_task
