"""Regression tests for automatic Shorts planning resilience."""
from app.services import ai_service


def _spoken_segments():
    return [
        {
            "start": float(i * 3),
            "end": float(i * 3 + 2.8),
            "text": f"Uma dica importante para melhorar resultados no canal, etapa {i}.",
        }
        for i in range(30)
    ]


def test_auto_falls_back_when_remote_ai_unavailable(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "clip_planning_provider", "auto")
    monkeypatch.setattr(ai_service.settings, "openai_api_key", "sk-test")

    def unavailable(*_args, **_kwargs):
        raise ai_service.AIPlanningError("OpenAI service unavailable (503)")

    monkeypatch.setattr(ai_service, "_select_clips_openai", unavailable)
    clips = ai_service.select_clips(_spoken_segments(), 90.0, 2, "Meu vídeo")
    assert len(clips) == 2
    assert all(15 <= clip.end - clip.start <= 60 for clip in clips)
    assert all("localmente" in clip.reason for clip in clips)


def test_explicit_openai_still_reports_error(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "clip_planning_provider", "openai")
    monkeypatch.setattr(ai_service.settings, "openai_api_key", "sk-test")

    def unavailable(*_args, **_kwargs):
        raise ai_service.AIPlanningError("OpenAI service unavailable (503)")

    monkeypatch.setattr(ai_service, "_select_clips_openai", unavailable)
    import pytest
    with pytest.raises(ai_service.AIPlanningError, match="503"):
        ai_service.select_clips(_spoken_segments(), 90.0, 2, "Meu vídeo")
