from types import SimpleNamespace

from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import align_asaas_environment
from app.database import Base
from app.models import TenantPlan
from app.routers.auth import register
from app.schemas import RegisterRequest


def test_asaas_modern_key_prefix_selects_matching_official_environment():
    sandbox = SimpleNamespace(
        asaas_api_key="$aact_hmlg_example",
        asaas_base_url="https://api.asaas.com/v3",
    )
    production = SimpleNamespace(
        asaas_api_key="$aact_prod_example",
        asaas_base_url="https://api-sandbox.asaas.com/v3",
    )

    assert align_asaas_environment(sandbox) == "sandbox"
    assert sandbox.asaas_base_url == "https://api-sandbox.asaas.com/v3"
    assert align_asaas_environment(production) == "production"
    assert production.asaas_base_url == "https://api.asaas.com/v3"


def test_asaas_custom_endpoint_and_legacy_key_are_not_mutated():
    custom = SimpleNamespace(asaas_api_key="$aact_hmlg_example", asaas_base_url="https://payments.example.test/v3")
    legacy = SimpleNamespace(asaas_api_key="legacy-key-without-environment-prefix", asaas_base_url="https://api.asaas.com/v3")

    assert align_asaas_environment(custom) == "custom"
    assert custom.asaas_base_url == "https://payments.example.test/v3"
    assert align_asaas_environment(legacy) == "production"
    assert legacy.asaas_base_url == "https://api.asaas.com/v3"


def test_new_registration_receives_real_trial_plan_without_touching_paid_plans():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = Session()
    try:
        response = Response()
        payload = register(
            RegisterRequest(
                name="Conta Teste",
                email="trial-check@example.com",
                password="SenhaTeste123",
                company_name="Empresa Teste",
            ),
            response,
            db,
        )

        plan = db.query(TenantPlan).filter(TenantPlan.tenant_id == payload["tenant_id"]).one()
        assert payload["plan_code"] == "trial"
        assert payload["billing_status"] == "trial"
        assert payload["processing_minutes_limit"] == 30
        assert payload["shorts_limit"] == 3
        assert payload["channel_limit"] == 1
        assert payload["user_limit"] == 1
        assert plan.plan_code == "trial"
        assert plan.billing_provider == "shortsflow"
        assert plan.unlimited is False
    finally:
        db.close()
        engine.dispose()
