from app.routers.editor_ai import presets
from app.services.editor_ai import PRESETS


def test_editor_ai_has_tiktok_shop_preset():
    assert "tiktok_shop_sales" in PRESETS
    assert PRESETS["tiktok_shop_sales"]["label"] == "TikTok Shop Vendas"
    assert float(PRESETS["tiktok_shop_sales"]["max_shot_seconds"]) > 0


def test_editor_presets_boot_without_auth_or_database():
    payload = presets()
    assert payload
    assert any(item["id"] == "tiktok_shop_sales" for item in payload)
    for item in payload:
        assert item["label"]
        assert item["description"]
        assert item["target"] == "TikTok Shop / Social Commerce"
