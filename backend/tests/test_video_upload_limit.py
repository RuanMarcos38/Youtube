"""Regressao: o limite do editor deve aceitar arquivos maiores que 500 MiB."""

from app.services.editor_ai import MAX_UPLOAD_BYTES, MAX_UPLOAD_MB


def test_editor_upload_limit_is_configured_in_mebibytes():
    assert MAX_UPLOAD_MB >= 1
    assert MAX_UPLOAD_BYTES == MAX_UPLOAD_MB * 1024 * 1024


def test_default_upload_limit_is_large_enough_for_long_videos():
    assert MAX_UPLOAD_BYTES >= 500 * 1024 * 1024
