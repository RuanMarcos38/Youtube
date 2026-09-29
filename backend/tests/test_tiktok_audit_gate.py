from fastapi import HTTPException

from app.routers import tiktok_auth


class _User:
    id = 123


class _Payload:
    clip_ids = [1]
    privacy_level = "PUBLIC_TO_EVERYONE"
    allow_comment = True
    allow_duet = True
    allow_stitch = False
    music_usage_confirmed = True


def test_creator_info_exposes_known_unaudited_block(monkeypatch):
    monkeypatch.setattr(
        tiktok_auth,
        "get_creator_info",
        lambda db, user_id, force=True: {
            "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
            "public_posting_blocked": False,
            "public_posting_block_reason": "",
            "comment_disabled": False,
            "duet_disabled": False,
            "stitch_disabled": False,
            "max_video_post_duration_sec": 60,
        },
    )
    monkeypatch.setattr(tiktok_auth, "clear_legacy_unaudited_state", lambda db, user_id: None)
    monkeypatch.setattr(
        tiktok_auth,
        "apply_unaudited_public_block",
        lambda db, user_id, creator: {
            **creator,
            "privacy_level_options": [],
            "public_posting_blocked": True,
            "public_posting_block_reason": "app não auditado",
        },
    )

    result = tiktok_auth.creator_info(user=_User(), db=object())
    assert result["public_posting_blocked"] is True
    assert result["privacy_level_options"] == []
    assert "auditado" in result["public_posting_block_reason"]


def test_upload_batch_does_not_report_false_queue_when_public_direct_post_is_blocked(monkeypatch):
    monkeypatch.setattr(tiktok_auth, "get_connection_status", lambda db, user_id: {"connected": True})
    monkeypatch.setattr(
        tiktok_auth,
        "get_creator_info",
        lambda db, user_id, force=True: {
            "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
            "public_posting_blocked": False,
            "public_posting_block_reason": "",
            "comment_disabled": False,
            "duet_disabled": False,
            "stitch_disabled": False,
            "max_video_post_duration_sec": 60,
        },
    )
    monkeypatch.setattr(tiktok_auth, "clear_legacy_unaudited_state", lambda db, user_id: None)
    monkeypatch.setattr(tiktok_auth, "recover_retryable_draft_uploads", lambda db, user_id: 0)
    monkeypatch.setattr(
        tiktok_auth,
        "apply_unaudited_public_block",
        lambda db, user_id, creator: {
            **creator,
            "privacy_level_options": [],
            "public_posting_blocked": True,
            "public_posting_block_reason": "O TikTok confirmou que este app ainda não está auditado.",
        },
    )

    try:
        tiktok_auth.upload_batch(payload=_Payload(), user=_User(), db=object())
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "auditado" in str(exc.detail)
    else:
        raise AssertionError("upload_batch deveria bloquear antes de informar fila aceita")
