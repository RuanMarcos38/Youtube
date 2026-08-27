from app.services import transcription


class _FakeTranscriptions:
    def create(self, **_kwargs):
        return type(
            "Transcript",
            (),
            {
                "text": "fala de teste",
                "segments": [{"start": 0.0, "end": 3.0, "text": "fala de teste"}],
            },
        )()


class _FakeAudio:
    transcriptions = _FakeTranscriptions()


class _FakeOpenAI:
    audio = _FakeAudio()

    def __init__(self, api_key: str):
        self.api_key = api_key


def test_transcribe_chunks_reports_progress_per_audio_file(tmp_path, monkeypatch):
    monkeypatch.setattr(transcription.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(transcription, "OpenAI", _FakeOpenAI)

    audio_files = []
    for index in range(3):
        path = tmp_path / f"audio_{index:03d}.mp3"
        path.write_bytes(b"fake audio")
        audio_files.append(path)

    events = []

    text, segments = transcription.transcribe_chunks(
        audio_files,
        progress_hook=lambda done, total, path: events.append((done, total, path.name)),
    )

    assert text == "fala de teste\nfala de teste\nfala de teste"
    assert [segment["start"] for segment in segments] == [0.0, 600.0, 1200.0]
    assert events == [
        (0, 3, "audio_000.mp3"),
        (1, 3, "audio_000.mp3"),
        (1, 3, "audio_001.mp3"),
        (2, 3, "audio_001.mp3"),
        (2, 3, "audio_002.mp3"),
        (3, 3, "audio_002.mp3"),
    ]
