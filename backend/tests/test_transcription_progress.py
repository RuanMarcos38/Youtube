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


class _FakeLocalSegment:
    def __init__(self, start: float, end: float, text: str):
        self.start = start
        self.end = end
        self.text = text


class _FakeLocalModel:
    def transcribe(self, _path: str, **_kwargs):
        return iter([_FakeLocalSegment(0.0, 3.0, "fala local")]), object()


def _audio_files(tmp_path):
    files = []
    for index in range(3):
        path = tmp_path / f"audio_{index:03d}.mp3"
        path.write_bytes(b"fake audio")
        files.append(path)
    return files


def test_transcribe_chunks_reports_progress_per_audio_file_with_openai(tmp_path, monkeypatch):
    monkeypatch.setattr(transcription.settings, "transcription_provider", "openai")
    monkeypatch.setattr(transcription.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(transcription, "OpenAI", _FakeOpenAI)

    events = []
    text, segments = transcription.transcribe_chunks(
        _audio_files(tmp_path),
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


def test_transcribe_chunks_uses_local_model_without_openai_credit(tmp_path, monkeypatch):
    monkeypatch.setattr(transcription.settings, "transcription_provider", "local")
    monkeypatch.setattr(transcription.settings, "openai_api_key", "")
    monkeypatch.setattr(transcription, "_get_local_model", lambda: _FakeLocalModel())

    events = []
    text, segments = transcription.transcribe_chunks(
        _audio_files(tmp_path),
        progress_hook=lambda done, total, path: events.append((done, total, path.name)),
    )

    assert text == "fala local\nfala local\nfala local"
    assert [segment["start"] for segment in segments] == [0.0, 600.0, 1200.0]
    assert events[-1] == (3, 3, "audio_002.mp3")
