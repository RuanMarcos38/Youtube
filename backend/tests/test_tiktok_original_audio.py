import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import tiktok_upload_task


def _has_pair(command: list[str], key: str, value: str) -> bool:
    return any(command[index:index + 2] == [key, value] for index in range(len(command) - 1))


def test_tiktok_file_keeps_rendered_video_and_uses_only_original_source_audio(tmp_path, monkeypatch):
    rendered = tmp_path / "clip_01.mp4"
    source = tmp_path / "source.mp4"
    rendered.write_bytes(b"rendered-short")
    source.write_bytes(b"original-source")
    clip = SimpleNamespace(
        id=17,
        file_path=str(rendered),
        start_seconds=12.5,
        end_seconds=27.0,
    )

    captured: dict[str, list[str]] = {}

    def fake_run(command, *, check, capture_output, text):
        assert check is True
        assert capture_output is True
        assert text is True
        captured["command"] = list(command)
        Path(command[-1]).write_bytes(b"prepared-tiktok-file")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(tiktok_upload_task.subprocess, "run", fake_run)

    output = tiktok_upload_task._prepare_tiktok_original_audio_file(clip)
    command = captured["command"]

    assert output != rendered
    assert rendered.read_bytes() == b"rendered-short"
    assert _has_pair(command, "-map", "0:v:0")
    assert _has_pair(command, "-map", "1:a:0")
    assert _has_pair(command, "-c:v", "copy")
    assert _has_pair(command, "-ss", "12.500")
    assert _has_pair(command, "-t", "14.500")

    input_positions = [index for index, value in enumerate(command) if value == "-i"]
    assert len(input_positions) == 2
    assert command[input_positions[0] + 1] == str(rendered)
    assert command[input_positions[1] + 1] == str(source)
    assert not any("sound-design" in value.lower() or "soundtrack" in value.lower() for value in command)


def test_tiktok_original_audio_fails_safe_when_source_is_missing(tmp_path):
    rendered = tmp_path / "clip_01.mp4"
    rendered.write_bytes(b"rendered-short")
    clip = SimpleNamespace(
        id=18,
        file_path=str(rendered),
        start_seconds=0.0,
        end_seconds=15.0,
    )

    with pytest.raises(RuntimeError, match="Arquivo-fonte original não encontrado"):
        tiktok_upload_task._prepare_tiktok_original_audio_file(clip)
