from app.config import Settings


def test_openai_model_env_alias(monkeypatch):
    monkeypatch.delenv("OPENAI_TEXT_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")

    settings = Settings(_env_file=None)

    assert settings.openai_text_model == "gpt-4.1"


def test_openai_model_env_alias_has_priority(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "gpt-5")

    settings = Settings(_env_file=None)

    assert settings.openai_text_model == "gpt-4.1"


def test_processing_speed_defaults(monkeypatch):
    for key in (
        "WORKER_CONCURRENCY",
        "LOCAL_WHISPER_BEAM_SIZE",
        "LOCAL_WHISPER_PARALLELISM",
        "LOCAL_WHISPER_CPU_THREADS",
        "AUDIO_CHUNK_SECONDS",
        "FFMPEG_PRESET",
        "FFMPEG_CRF",
        "FFMPEG_THREADS_PER_JOB",
        "WORKER_POLL_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.worker_concurrency == 5
    assert settings.worker_poll_seconds == 1.0
    assert settings.local_whisper_beam_size == 1
    assert settings.local_whisper_parallelism == 2
    assert settings.local_whisper_cpu_threads == 0
    assert settings.audio_chunk_seconds == 1200
    assert settings.ffmpeg_preset == "veryfast"
    assert settings.ffmpeg_crf == 21
    assert settings.ffmpeg_threads_per_job == 2
