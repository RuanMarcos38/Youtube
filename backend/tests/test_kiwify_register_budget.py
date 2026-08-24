from pathlib import Path


def test_kiwify_register_has_total_deadline_and_no_product_scan():
    source = Path("app/services/kiwify_api.py").read_text(encoding="utf-8")
    assert "TOTAL_BUDGET_SECONDS = 15.0" in source
    register_source = source.split("def register_webhook(", 1)[1]
    assert "_resolve_checkout_products(" not in register_source
    assert "deadline = time.monotonic() + TOTAL_BUDGET_SECONDS" in register_source
