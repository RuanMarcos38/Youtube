from app.services.tiktok_upload import MAX_CHUNK_BYTES, _chunk_plan
from app.services.youtube_search import MIN_SOURCE_DURATION_SECONDS, _duration_seconds


def test_youtube_source_minimum_is_fifty_minutes():
    assert MIN_SOURCE_DURATION_SECONDS == 3000
    assert _duration_seconds("PT49M59S") == 2999
    assert _duration_seconds("PT50M") == 3000
    assert _duration_seconds("PT1H20M") == 4800


def test_tiktok_chunk_plan_never_exceeds_maximum_chunk_size():
    chunk_size, count = _chunk_plan(MAX_CHUNK_BYTES + 1)
    assert count >= 2
    assert chunk_size <= MAX_CHUNK_BYTES
    assert chunk_size * count >= MAX_CHUNK_BYTES + 1


def test_tiktok_single_small_file_uses_one_chunk():
    chunk_size, count = _chunk_plan(4 * 1024 * 1024)
    assert count == 1
    assert chunk_size == 4 * 1024 * 1024
