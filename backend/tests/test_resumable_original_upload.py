"""Regression coverage for isolated, tenant-scoped resumable uploads."""
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.upload_resumable import MAX_BYTES, PART_BYTES, UploadStart, _offset, _paths


def test_chunks_fit_inside_reverse_proxy_request_limit():
    assert PART_BYTES == 8 * 1024 * 1024
    assert MAX_BYTES >= 5 * 1024 * 1024 * 1024


def test_session_path_reuses_existing_per_user_upload_directory():
    upload_id = uuid4().hex
    target, part, manifest = _paths(123, upload_id, ".mp4")
    assert f"/users/123/uploads/{upload_id}/" in str(target)
    assert target.name == "source.mp4"
    assert part.name == "source.mp4.part"
    assert manifest.name == "manifest.json"


def test_invalid_session_id_rejected_before_filesystem_access():
    with pytest.raises(ValueError):
        _paths(123, "../../etc/passwd", ".mp4")


def test_zero_length_upload_rejected():
    with pytest.raises(Exception):
        UploadStart(name="video.mp4", size=0, requested_clips=1, rights_confirmed=True)


def test_missing_partial_file_starts_at_zero(tmp_path: Path):
    assert _offset(tmp_path / "missing.part") == 0
