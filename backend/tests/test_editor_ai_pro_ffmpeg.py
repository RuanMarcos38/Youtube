import shutil
import subprocess

import pytest

from app.services.editor_ai_pro import (
    MotionCue,
    _render_reframed,
    _write_original_soundtrack,
    _write_pro_ass,
)
from app.services.editor_audio_mix import mix_sound_design


pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg/FFprobe required")


def _run(command):
    subprocess.run(command, check=True, capture_output=True, text=True)


def test_professional_render_and_audio_ducking_pipeline(tmp_path):
    source = tmp_path / "source.mp4"
    _run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=1.2",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1.2",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(source),
    ])

    captions = [{"start": 0.05, "end": 1.0, "text": "TESTE PREMIUM", "highlighted_words": ["premium"]}]
    ass = _write_pro_ass(
        captions,
        tmp_path / "captions.ass",
        "impact",
        True,
        [MotionCue(start=0.12, end=0.9, text="IMPACTO PREMIUM", emphasis="impact", position="center")],
    )
    reframed = tmp_path / "reframed.mp4"
    _render_reframed(
        source,
        reframed,
        [{"source_in": 0.0, "source_out": 1.2, "timeline_in": 0.0, "timeline_out": 1.2, "enabled": True}],
        [0.5],
        ass,
        [{"timeline_in": 0.2, "timeline_out": 0.95, "enabled": True}],
        preset="tiktok_shop_sales",
        intensity="high",
    )
    assert reframed.is_file() and reframed.stat().st_size > 1000

    music = _write_original_soundtrack(tmp_path / "music.wav", 1.2, [0.4, 0.8], "energetic")
    final = tmp_path / "final.mp4"
    mix_sound_design(reframed, music, final, 0.18)
    assert final.is_file() and final.stat().st_size > 1000

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "csv=p=0", str(final)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "video,1080,1920" in probe
    assert "audio" in probe
