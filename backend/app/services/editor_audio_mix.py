from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import settings


def mix_sound_design(video: Path, soundtrack: Path, output: Path, volume: float, *, loop_music: bool = False) -> None:
    """Mix a music bed under the processed voice using FFmpeg side-chain ducking.

    Voice is explicitly split into two branches because FFmpeg filter pads are
    consumed once. One branch drives the side-chain compressor and the other is
    preserved for the final voice/music mix.
    """
    command = [settings.ffmpeg_binary, "-y", "-i", str(video)]
    if loop_music:
        command.extend(["-stream_loop", "-1"])
    command.extend(["-i", str(soundtrack)])
    command.extend([
        "-filter_complex",
        f"[0:a]volume=1.0,asplit=2[voice_sc][voice_mix];"
        f"[1:a]volume={volume:.3f},highpass=f=45,lowpass=f=15000[music];"
        "[music][voice_sc]sidechaincompress=threshold=0.055:ratio=6:attack=18:release=320[ducked];"
        "[voice_mix][ducked]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[aout]",
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", "-movflags", "+faststart", str(output),
    ])
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Executável não encontrado: {settings.ffmpeg_binary}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "Falha no mix profissional de áudio")[-6000:]
        raise RuntimeError(detail) from exc
