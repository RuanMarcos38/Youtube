from types import SimpleNamespace

from app.routers.admin_insights import monthly_equivalent_cents


def test_monthly_subscription_keeps_contract_value():
    plan = SimpleNamespace(
        subscription_value_cents=14990,
        billing_cycle="monthly",
        plan_code="pro",
    )
    assert monthly_equivalent_cents(plan) == 14990


def test_yearly_subscription_is_normalized_to_mrr():
    plan = SimpleNamespace(
        subscription_value_cents=599900,
        billing_cycle="yearly",
        plan_code="agency",
    )
    assert monthly_equivalent_cents(plan) == round(599900 / 12)


def test_catalog_price_is_used_only_when_stored_contract_value_is_missing():
    plan = SimpleNamespace(
        subscription_value_cents=0,
        billing_cycle="monthly",
        plan_code="creator",
    )
    assert monthly_equivalent_cents(plan) == 7990
