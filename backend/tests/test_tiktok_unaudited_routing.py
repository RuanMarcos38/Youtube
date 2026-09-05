from types import SimpleNamespace

from app.services.tiktok_upload_task import _unaudited_account_requires_upload_fallback


def test_private_account_self_only_uses_direct_post(monkeypatch):
    monkeypatch.setattr(
        "app.services.tiktok_upload_task.get_creator_info",
        lambda db, user_id: {
            "privacy_level_options": ["FOLLOWER_OF_CREATOR", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"],
        },
    )
    post = SimpleNamespace(user_id=1, privacy_level="SELF_ONLY")
    assert _unaudited_account_requires_upload_fallback(object(), post) is False


def test_public_account_self_only_keeps_upload_fallback(monkeypatch):
    monkeypatch.setattr(
        "app.services.tiktok_upload_task.get_creator_info",
        lambda db, user_id: {
            "privacy_level_options": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"],
        },
    )
    post = SimpleNamespace(user_id=1, privacy_level="SELF_ONLY")
    assert _unaudited_account_requires_upload_fallback(object(), post) is True


def test_non_self_only_never_bypasses_unaudited_gate(monkeypatch):
    monkeypatch.setattr(
        "app.services.tiktok_upload_task.get_creator_info",
        lambda db, user_id: {
            "privacy_level_options": ["FOLLOWER_OF_CREATOR", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"],
        },
    )
    post = SimpleNamespace(user_id=1, privacy_level="FOLLOWER_OF_CREATOR")
    assert _unaudited_account_requires_upload_fallback(object(), post) is True
