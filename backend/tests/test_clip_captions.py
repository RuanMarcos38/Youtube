import pytest
from pydantic import ValidationError

from app.routers.clips import _caption_removal_requested, _normalize_subtitle_text
from app.schemas import ClipCaptionUpdateRequest, UploadRequest


def test_plain_caption_text_is_converted_to_srt():
    result = _normalize_subtitle_text("Legenda corrigida", 4.25)

    assert result == "1\n00:00:00,000 --> 00:00:04,250\nLegenda corrigida\n"


def test_existing_srt_is_preserved():
    source = "1\n00:00:00,000 --> 00:00:01,000\nOi\n"

    assert _normalize_subtitle_text(source, 5.0) == source


def test_empty_subtitle_explicitly_requests_caption_removal():
    payload = ClipCaptionUpdateRequest(
        caption_position="bottom",
        caption_margin_v=120,
        caption_font_size=18,
        subtitle_srt="   ",
    )

    assert _caption_removal_requested(payload) is True


def test_unchanged_subtitle_does_not_request_caption_removal():
    payload = ClipCaptionUpdateRequest(
        caption_position="bottom",
        caption_margin_v=120,
        caption_font_size=18,
        subtitle_srt=None,
    )

    assert _caption_removal_requested(payload) is False


def test_caption_settings_reject_invalid_ranges():
    with pytest.raises(ValidationError):
        ClipCaptionUpdateRequest(caption_position="bottom", caption_margin_v=10, caption_font_size=40)


def test_upload_request_defaults_to_public():
    assert UploadRequest().privacy_status == "public"
