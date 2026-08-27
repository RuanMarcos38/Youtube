from app.services import ai_service


def _segments(bucket_count: int = 12, per_bucket: int = 31) -> list[dict]:
    rows = []
    for bucket in range(bucket_count):
        for index in range(per_bucket):
            start = float(bucket * 600 + index * 8)
            rows.append(
                {
                    "start": start,
                    "end": start + 4.0,
                    "text": f"bucket-{bucket} insight-{index} " + ("palavra " * 80),
                }
            )
    return rows


def test_timestamped_transcript_uses_distributed_budget_for_long_videos(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "max_transcript_chars", 180000)

    transcript = ai_service._timestamped_transcript(_segments())

    assert len(transcript) <= ai_service.CLIP_SELECTION_TRANSCRIPT_LIMIT
    assert "Excerpt 1/12" in transcript
    assert "Excerpt 12/12" in transcript
    assert "bucket-0" in transcript
    assert "bucket-11" in transcript


class _FakeResponses:
    def __init__(self):
        self.call_lengths: list[int] = []

    def parse(self, *, input, **_kwargs):
        user_message = next(item["content"] for item in input if item["role"] == "user")
        self.call_lengths.append(len(user_message))
        if len(self.call_lengths) == 1:
            raise RuntimeError("rate_limit_exceeded: tokens per min limit exceeded")
        return type(
            "Response",
            (),
            {
                "output_parsed": ai_service.ClipPlan(
                    clips=[
                        ai_service.ClipCandidate(
                            start=10.0,
                            end=30.0,
                            hook="Um gancho forte",
                            reason="Momento claro e autocontido.",
                            title="Gancho forte para Shorts",
                            description="Descricao SEO do corte.",
                            copy="Comente sua opiniao.",
                            tags=["shorts", "podcast", "marketing"],
                        )
                    ]
                )
            },
        )()


def test_select_clips_retries_with_smaller_transcript_on_rate_limit(monkeypatch):
    fake_responses = _FakeResponses()

    class _FakeOpenAI:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.responses = fake_responses

    monkeypatch.setattr(ai_service.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(ai_service.settings, "max_transcript_chars", 180000)
    monkeypatch.setattr(ai_service, "OpenAI", _FakeOpenAI)

    clips = ai_service.select_clips(_segments(), 7200.0, 1, "Podcast longo")

    assert len(clips) == 1
    assert len(fake_responses.call_lengths) == 2
    assert fake_responses.call_lengths[1] < fake_responses.call_lengths[0]
