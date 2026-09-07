import inspect

import pytest

from app.routers.automation import AutomaticModeUpdate, _payload_dict, _protected_config, _protected_status
from app.services import automatic_mode


def test_caption_removal_rule_cannot_be_disabled():
    with pytest.raises(ValueError, match="obrigatória"):
        _payload_dict(AutomaticModeUpdate(remove_generated_captions=False))


def test_caption_removal_rule_is_always_exposed_as_enabled():
    config = _protected_config({"enabled": True})
    status = _protected_status({"enabled": True})
    assert config["remove_generated_captions"] is True
    assert status["caption_removal_required"] is True


def test_youtube_auto_queue_only_accepts_caption_clean_clips():
    source = inspect.getsource(automatic_mode._queue_youtube_due)
    assert 'Clip.subtitle_path == ""' in source


def test_tiktok_auto_queue_only_accepts_caption_clean_clips():
    source = inspect.getsource(automatic_mode._queue_tiktok_due)
    assert 'Clip.subtitle_path == ""' in source


def test_caption_cleaning_happens_before_distribution():
    source = inspect.getsource(automatic_mode.run_user_automatic_mode)
    clean_index = source.index("_clean_ready_clips")
    youtube_index = source.index("_queue_youtube_due")
    tiktok_index = source.index("_queue_tiktok_due")
    assert clean_index < youtube_index < tiktok_index
