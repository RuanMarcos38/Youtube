from pathlib import Path

from app.services import ffmpeg_service


def test_vertical_render_fills_short_canvas_without_stretching(monkeypatch, tmp_path):
    commands: list[list[str]] = []

    monkeypatch.setattr(ffmpeg_service, "_run", lambda command: commands.append(command) or "")
    monkeypatch.setattr(ffmpeg_service.settings, "ffmpeg_crf", 26)
    monkeypatch.setattr(ffmpeg_service.settings, "ffmpeg_preset", "veryfast")

    output = tmp_path / "clip.mp4"
    ffmpeg_service.render_vertical_clip(
        Path("source.mp4"),
        output,
        10.0,
        25.0,
    )

    assert len(commands) == 1
    command = commands[0]
    vf = command[command.index("-vf") + 1]

    assert "force_original_aspect_ratio=increase" in vf
    assert "flags=lanczos" in vf
    assert "crop=1080:1920" in vf
    assert "setsar=1" in vf
    assert "force_original_aspect_ratio=decrease" not in vf
    assert "pad=1080:1920" not in vf

    assert command[command.index("-crf") + 1] == "18"
    assert command[command.index("-b:a") + 1] == "192k"
    assert command[command.index("-ar") + 1] == "48000"
    assert command[command.index("-profile:v") + 1] == "high"
    assert command[command.index("-level") + 1] == "4.2"


def test_vertical_render_preserves_existing_higher_quality_setting(monkeypatch, tmp_path):
    commands: list[list[str]] = []

    monkeypatch.setattr(ffmpeg_service, "_run", lambda command: commands.append(command) or "")
    monkeypatch.setattr(ffmpeg_service.settings, "ffmpeg_crf", 16)

    ffmpeg_service.render_vertical_clip(
        Path("source.mp4"),
        tmp_path / "clip.mp4",
        0.0,
        10.0,
    )

    command = commands[0]
    assert command[command.index("-crf") + 1] == "16"
