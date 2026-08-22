from app.services.editor_ai import PRESETS


def test_editor_ai_has_tiktok_shop_preset():
    assert "tiktok_shop_sales" in PRESETS
    assert PRESETS["tiktok_shop_sales"]["label"] == "TikTok Shop Vendas"
    assert float(PRESETS["tiktok_shop_sales"]["max_shot_seconds"]) > 0
