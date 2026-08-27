from app.services import ai_video


def test_ai_video_options_reports_available_when_configured(monkeypatch):
    monkeypatch.setattr(ai_video.settings, "ai_video_enabled", True)
    monkeypatch.setattr(ai_video.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(ai_video.settings, "openai_api_key", "")

    options = ai_video.ai_video_options()

    assert options["available"] is True
    assert options["defaults"]["aspect_ratio"] == "9:16"
    assert options["audio_supported"] is True
    assert options["prompt_improvement_available"] is False


def test_queue_ai_video_project_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_video.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(ai_video.settings, "ai_video_enabled", True)
    monkeypatch.setattr(ai_video.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(ai_video.settings, "veo_fast_model", "veo-test-fast")

    first = ai_video.queue_ai_video_project(
        user_id=10,
        tenant_id=20,
        prompt="Video vertical de produto premium em estudio moderno",
        request_id="same-request",
    )
    second = ai_video.queue_ai_video_project(
        user_id=10,
        tenant_id=20,
        prompt="Outro prompt não deve criar duplicado",
        request_id="same-request",
    )

    assert first["id"] == second["id"]
    assert first["status"] == ai_video.AI_VIDEO_QUEUED
    assert first["ai_video_generation"]["provider"] == "google_veo"
    assert first["ai_video_generation"]["model"] == "veo-test-fast"


def test_google_veo_submit_uses_supported_parameters(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {"name": "operations/test"}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(ai_video.httpx, "post", fake_post)
    monkeypatch.setattr(ai_video.settings, "ai_video_request_timeout_seconds", 12)

    provider = ai_video.GoogleVeoProvider("secret")
    operation = provider.submit(
        ai_video.AiVideoRequest(
            prompt="Prompt",
            model="veo-test",
            aspect_ratio="9:16",
            resolution="1080p",
            duration_seconds=8,
            style="cinematic",
        )
    )

    assert operation == "operations/test"
    assert captured["url"].endswith("/models/veo-test:predictLongRunning")
    assert captured["headers"]["x-goog-api-key"] == "secret"
    assert captured["json"]["parameters"] == {
        "aspectRatio": "9:16",
        "durationSeconds": "8",
        "resolution": "1080p",
        "personGeneration": "allow_all",
    }
