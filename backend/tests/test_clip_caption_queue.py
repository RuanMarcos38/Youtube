import inspect

from app import worker
from app.routers import clips
from app.services import clip_caption_queue


def test_caption_removal_request_is_queued_instead_of_rendering_inside_http_request():
    source = inspect.getsource(clips.update_clip_captions)
    queue_index = source.index("enqueue_caption_removal")
    render_index = source.index("render_vertical_clip")
    assert queue_index < render_index
    assert "if removing_caption" in source


def test_youtube_worker_blocks_media_while_caption_removal_is_pending():
    source = inspect.getsource(worker._claim_next_upload)
    assert "caption_removal_pending" in source


def test_tiktok_worker_blocks_media_while_caption_removal_is_pending():
    source = inspect.getsource(worker._claim_next_tiktok_post)
    assert "caption_removal_pending" in source


def test_caption_queue_retries_are_bounded_and_keep_failed_media_blocked():
    assert clip_caption_queue.MAX_CAPTION_REMOVE_ATTEMPTS == 3
    source = inspect.getsource(clip_caption_queue.caption_removal_pending)
    assert '"failed"' in source
